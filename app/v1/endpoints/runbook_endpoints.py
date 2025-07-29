from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID
from sqlalchemy import desc

from app.db.models.runbook_step import RunbookStep
from app.db.models.incident_type import IncidentType
from app.v1.schemas.runbook import RunbookCreate, RunbookUpdate, RunbookInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.runbook_repository import RunbookRepository
from app.db.models.runbook import Runbook
from app.services.elasticsearch.runbook_service import index_runbook
from app.utils.response import success_response, error_response
from app.db.models.response_action import ResponseAction
from sqlalchemy import func
import datetime

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbooks = RunbookRepository(db, redis).get_all()
    return success_response(serialize(runbooks, RunbookInDB), "Runbooks fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbooks = RunbookRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(runbooks, RunbookInDB), "Soft deleted runbooks fetched successfully.")

@router.get("/count")
def count_total_runbooks(db: Session = Depends(get_db)):
    count = db.query(Runbook).filter(Runbook.is_deleted == False).count()
    return success_response({"total": count}, "Total runbooks counted")

@router.get("/count/running")
def count_running_runbooks(db: Session = Depends(get_db)):
    count = db.query(ResponseAction).filter(
        ResponseAction.status == "In Progress",
        ResponseAction.is_deleted == False
    ).count()
    return success_response({"running_now": count}, "Running runbooks counted.")

@router.get("/average-success-rate")
def get_average_success_rate(db: Session = Depends(get_db)):
    total = db.query(func.count(ResponseAction.action_id)).filter(ResponseAction.is_deleted == False).scalar()
    successful = db.query(func.count(ResponseAction.action_id)).filter(
        ResponseAction.status == "Completed",
        ResponseAction.is_deleted == False
    ).scalar()

    success_rate = round((successful / total) * 100, 2) if total else 0.0
    return success_response({"average_success_rate": success_rate}, "Average success rate computed.")


@router.get("/runbooks/{runbook_id}/last-run")
def get_last_run_time(runbook_id: UUID, db: Session = Depends(get_db)):
    last_run = (
        db.query(ResponseAction.started_at)
        .filter(
            ResponseAction.runbook_id == runbook_id,
            ResponseAction.is_deleted == False,
            ResponseAction.started_at != None
        )
        .order_by(desc(ResponseAction.started_at))
        .first()
    )

    if not last_run or not last_run[0]:
        return success_response({"last_run": None}, "No run history found.")

    return success_response({"last_run": last_run[0].strftime("%Y-%m-%d %H:%M")}, "Last run fetched.")


@router.get("/runbooks/{runbook_id}/last-completed")
def get_last_completed_time(runbook_id: UUID, db: Session = Depends(get_db)):
    last_completed = (
        db.query(ResponseAction.completed_at)
        .filter(
            ResponseAction.runbook_id == runbook_id,
            ResponseAction.is_deleted == False,
            ResponseAction.completed_at != None
        )
        .order_by(desc(ResponseAction.completed_at))
        .first()
    )

    if not last_completed or not last_completed[0]:
        return success_response({"last_completed": None}, "No completed runs found.")

    return success_response({
        "last_completed": last_completed[0].strftime("%Y-%m-%d %H:%M")
    }, "Last completed timestamp fetched.")

@router.get("/runbooks/{runbook_id}/average-duration")
def get_average_duration(runbook_id: UUID, db: Session = Depends(get_db)):
    durations = (
        db.query(
            func.avg(
                func.extract('epoch', ResponseAction.completed_at - ResponseAction.started_at)
            ).label("avg_duration_seconds")
        )
        .filter(
            ResponseAction.runbook_id == runbook_id,
            ResponseAction.started_at != None,
            ResponseAction.completed_at != None,
            ResponseAction.is_deleted == False
        )
        .scalar()
    )

    if durations is None:
        return success_response({"average_duration": None}, "No completed runs found for this runbook.")

    # Convert seconds to HH:MM:SS format
    
    formatted_duration = str(datetime.timedelta(seconds=int(durations)))

    return success_response({
        "average_duration": formatted_duration
    }, "Average run duration fetched.")


@router.get("/card-view")
def get_runbook_cards(db: Session = Depends(get_db)):
    

    runbooks = db.query(Runbook).filter(Runbook.is_deleted == False).all()
    cards = []

    for rb in runbooks:
        # Type from IncidentType
        incident_type = rb.incident_type.name if rb.incident_type else None

        # Count Steps
        step_count = db.query(RunbookStep).filter(RunbookStep.runbook_id == rb.runbook_id).count()

        # Last run (started_at)
        last_run = db.query(ResponseAction.started_at)\
            .filter(ResponseAction.runbook_id == rb.runbook_id, ResponseAction.started_at != None)\
            .order_by(ResponseAction.started_at.desc()).first()

        # Completed_at
        completed_at = db.query(ResponseAction.completed_at)\
            .filter(ResponseAction.runbook_id == rb.runbook_id, ResponseAction.completed_at != None)\
            .order_by(ResponseAction.completed_at.desc()).first()

        # Duration (average)
        avg_seconds = db.query(
            func.avg(func.extract('epoch', ResponseAction.completed_at - ResponseAction.started_at))
        ).filter(
            ResponseAction.runbook_id == rb.runbook_id,
            ResponseAction.started_at != None,
            ResponseAction.completed_at != None
        ).scalar()
        duration = str(datetime.timedelta(seconds=int(avg_seconds))) if avg_seconds else None

        # Success Rate
        total = db.query(ResponseAction).filter(ResponseAction.runbook_id == rb.runbook_id).count()
        completed = db.query(ResponseAction).filter(
            ResponseAction.runbook_id == rb.runbook_id,
            ResponseAction.status == "Completed"
        ).count()
        success_rate = round((completed / total) * 100, 2) if total > 0 else None

        cards.append({
            "id": str(rb.runbook_id),
            "title": rb.name,
            "type": incident_type,
            "description": rb.description,
            "last_run": last_run[0].strftime("%Y-%m-%d %H:%M") if last_run and last_run[0] else None,
            "completed_at": completed_at[0].strftime("%Y-%m-%d %H:%M") if completed_at and completed_at[0] else None,
            "average_duration": duration,
            "success_rate": f"{success_rate}%" if success_rate is not None else None,
            "steps_count": step_count
        })

    return success_response(cards, "Runbook card summaries fetched.")

@router.get("/executions/recent")
def get_recent_runbook_executions(db: Session = Depends(get_db)):
    recent_actions = db.query(ResponseAction).filter(
        ResponseAction.is_deleted == False
    ).order_by(ResponseAction.started_at.desc()).limit(10).all()

    response = []

    for action in recent_actions:
        runbook = action.runbook
        runbook_name = runbook.name if runbook else None

        # Estimate duration from past completions
        avg_seconds = db.query(func.avg(func.extract('epoch', ResponseAction.completed_at - ResponseAction.started_at))).filter(
            ResponseAction.runbook_id == action.runbook_id,
            ResponseAction.completed_at != None,
            ResponseAction.started_at != None
        ).scalar()

        est_completion = (
            action.started_at + datetime.timedelta(seconds=float(avg_seconds))
            if action.started_at and avg_seconds
            else None
        )

        # Get number of steps
        total_steps = db.query(RunbookStep).filter(RunbookStep.runbook_id == action.runbook_id).count()

        # Determine progress
        progress = None
        if action.status == "Completed":
            progress = 100
        elif action.status == "Pending" and total_steps > 0:
            progress = 0
        elif action.status == "In Progress":
            # Optional logic: assume 75% if no detailed step progress available
            progress = 75

        # Fake step name (or fetch later)
        current_step = "Processing..." if action.status == "In Progress" else "Backup verification completed" if action.status == "Completed" else None

        response.append({
            "execution_id": f"EXE-{str(action.action_id)[-4:]}",  # last 4 chars as suffix
            "title": runbook_name,
            "status": action.status,
            "progress": progress,
            "current_step": current_step,
            "started_at": action.started_at.strftime("%Y-%m-%d %H:%M:%S") if action.started_at else None,
            "estimated_completion": est_completion.strftime("%Y-%m-%d %H:%M:%S") if est_completion else None
        })

    return success_response(response, "Recent runbook executions.")

@router.get("/{runbook_id}")
def get_by_id(runbook_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbook = RunbookRepository(db, redis).get_by_id(runbook_id)
    if not runbook:
        return error_response("Runbook not found", 404)
    return success_response(serialize(runbook, RunbookInDB), "Runbook fetched successfully.")


@router.post("/")
def create(data: RunbookCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbook = RunbookRepository(db, redis).create(data.dict())
    index_runbook(runbook)
    return success_response(serialize(runbook, RunbookInDB), "Runbook created successfully.", 201)


@router.put("/{runbook_id}")
def update(runbook_id: UUID, data: RunbookUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RunbookRepository(db, redis).update(runbook_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Runbook not found", 404)
    db.refresh(result)
    index_runbook(result)
    return success_response(serialize(result, RunbookInDB), "Runbook updated successfully.")


@router.delete("/soft/{runbook_id}")
def soft_delete(runbook_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RunbookRepository(db, redis).soft_delete(runbook_id)
    if not result:
        return error_response("Runbook not found", 404)
    return success_response(serialize(result, RunbookInDB), "Runbook soft deleted successfully.")


@router.put("/restore/{runbook_id}")
def restore(runbook_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RunbookRepository(db, redis).restore(runbook_id)
    if not result:
        return error_response("Runbook not found", 404)
    return success_response(serialize(result, RunbookInDB), "Runbook restored successfully.")


@router.delete("/hard/{runbook_id}")
def hard_delete(runbook_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RunbookRepository(db, redis).hard_delete(runbook_id)
    if not result:
        return error_response("Runbook not found", 404)
    return success_response(serialize(result, RunbookInDB), "Runbook permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = RunbookRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, RunbookInDB), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    runbooks = db.query(Runbook).filter_by(is_deleted=False).all()
    for runbook in runbooks:
        index_runbook(runbook)
    return success_response({"count": len(runbooks)}, "All runbooks indexed to Elasticsearch.")
