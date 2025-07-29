from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.runbook_step import RunbookStepCreate, RunbookStepUpdate, RunbookStepRead
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.runbook_step_repository import RunbookStepRepository
from app.db.models.runbook_step import RunbookStep
from app.services.elasticsearch.runbook_step_service import index_runbook_step
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    steps = RunbookStepRepository(db, redis).get_all()
    return success_response(serialize(steps, RunbookStepRead), "Runbook steps fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    steps = RunbookStepRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(steps, RunbookStepRead), "Soft deleted runbook steps fetched successfully.")


@router.get("/{step_id}")
def get_by_id(step_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    step = RunbookStepRepository(db, redis).get_by_id(step_id)
    if not step:
        return error_response("Runbook step not found", 404)
    return success_response(serialize(step, RunbookStepRead), "Runbook step fetched successfully.")


@router.post("/")
def create(data: RunbookStepCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    step = RunbookStepRepository(db, redis).create(data.dict())
    index_runbook_step(step)
    return success_response(serialize(step, RunbookStepRead), "Runbook step created successfully.", 201)


@router.put("/{step_id}")
def update(step_id: UUID, data: RunbookStepUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RunbookStepRepository(db, redis).update(step_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Runbook step not found", 404)
    db.refresh(result)
    index_runbook_step(result)
    return success_response(serialize(result, RunbookStepRead), "Runbook step updated successfully.")


@router.delete("/soft/{step_id}")
def soft_delete(step_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RunbookStepRepository(db, redis).soft_delete(step_id)
    if not result:
        return error_response("Runbook step not found", 404)
    return success_response(serialize(result, RunbookStepRead), "Runbook step soft deleted successfully.")


@router.put("/restore/{step_id}")
def restore(step_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RunbookStepRepository(db, redis).restore(step_id)
    if not result:
        return error_response("Runbook step not found", 404)
    return success_response(serialize(result, RunbookStepRead), "Runbook step restored successfully.")


@router.delete("/hard/{step_id}")
def hard_delete(step_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RunbookStepRepository(db, redis).hard_delete(step_id)
    if not result:
        return error_response("Runbook step not found", 404)
    return success_response(serialize(result, RunbookStepRead), "Runbook step permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = RunbookStepRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, RunbookStepRead), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    steps = db.query(RunbookStep).filter_by(is_deleted=False).all()
    for step in steps:
        index_runbook_step(step)
    return success_response({"count": len(steps)}, "All runbook steps indexed to Elasticsearch.")
