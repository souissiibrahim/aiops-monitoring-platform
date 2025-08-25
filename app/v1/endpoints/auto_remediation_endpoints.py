from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from app.db.session import get_db
from app.db.models.runbook import Runbook
from app.db.models.runbook_step import RunbookStep
from app.db.models.response_action import ResponseAction
from app.utils.response import success_response
from datetime import timedelta
from app.v1.endpoints.response_action_endpoints import serialize
from app.v1.schemas.response_action import ResponseActionRead

router = APIRouter()

def safe_iso(dt):
    return dt.isoformat() if dt else None


def format_duration(started_at, completed_at):
    if not started_at or not completed_at:
        return "Failed"
    duration = completed_at - started_at
    minutes, seconds = divmod(int(duration.total_seconds()), 60)
    return f"{minutes}m {seconds}s"

@router.get("/count/active")
def count_runbooks_with_auto_steps(db: Session = Depends(get_db)):
    count = db.query(RunbookStep.runbook_id).join(Runbook).filter(
        RunbookStep.action_type.ilike('%auto%'),
        Runbook.is_deleted == False
    ).distinct().count()

    return success_response({"active_rules": count}, "Runbooks with at least one auto remediation step counted.")


@router.get("/count/running")
def count_running_auto_remediations(db: Session = Depends(get_db)):
    count = db.query(RunbookStep.runbook_id).join(ResponseAction).filter(
        RunbookStep.action_type.ilike('%auto%'),
        ResponseAction.status.in_(["Pending", "In Progress"]),
        ResponseAction.is_deleted == False
    ).distinct().count()

    return success_response({"active_rules": count}, "Active auto remediation rules counted.")


@router.get("/success-rate")
def get_auto_remediation_success_rate(db: Session = Depends(get_db)):
    total = db.query(func.count(ResponseAction.action_id)).join(RunbookStep).filter(
        RunbookStep.action_type.ilike('%auto%')
    ).scalar()

    completed = db.query(func.count(ResponseAction.action_id)).join(RunbookStep).filter(
        RunbookStep.action_type.ilike('%auto%'),
        ResponseAction.status == "Completed"
    ).scalar()

    success_rate = (completed / total * 100) if total else 0.0
    return success_response({"success_rate": round(success_rate, 2)}, "Success rate of auto remediations.")


@router.get("/time-saved")
def get_estimated_time_saved(db: Session = Depends(get_db)):
    actions = db.query(ResponseAction).join(RunbookStep).filter(
        RunbookStep.action_type.ilike('%auto%'),
        ResponseAction.started_at.isnot(None),
        ResponseAction.completed_at.isnot(None)
    ).all()

    total_seconds = sum([
        (action.completed_at - action.started_at).total_seconds()
        for action in actions
    ])
    total_hours = round(total_seconds / 3600, 2)

    return success_response({"time_saved": total_hours}, "Estimated time saved by auto remediations.")

@router.get("/auto-remediation/cards")
def get_auto_remediation_cards(db: Session = Depends(get_db)):
    runbooks = (
        db.query(Runbook)
        .join(RunbookStep)
        .filter(RunbookStep.action_type.ilike('%auto%'))
        .options(joinedload(Runbook.runbook_steps), joinedload(Runbook.incident_type))
        .all()
    )

    cards = []
    for runbook in runbooks:
        auto_step = next((step for step in runbook.runbook_steps if step.action_type and "auto" in step.action_type.lower()), None)
        if not auto_step:
            continue

        response_actions = db.query(ResponseAction).filter(
            ResponseAction.runbook_id == runbook.runbook_id,
            ResponseAction.step_id == auto_step.step_id
        ).all()

        last_triggered = max((ra.started_at for ra in response_actions if ra.started_at), default=None)
        total = len(response_actions)
        completed = sum(1 for ra in response_actions if ra.status == "Completed")
        success_rate = round((completed / total * 100), 1) if total else 0.0
        status_label = "Active" if any(ra.status in ["Pending", "In Progress"] for ra in response_actions) else "Inactive"
        incident_category = runbook.incident_type.category if runbook.incident_type else "Unknown"

        cards.append({
            "rule_id": str(runbook.runbook_id),
            "title": runbook.name,
            "description": runbook.description,
            "trigger_condition": auto_step.success_condition,
            "remediation_action": auto_step.description,
            "last_triggered": safe_iso(last_triggered),
            "success_rate": success_rate,
            "labels": [incident_category, status_label]
        })

    return success_response(cards, "Auto remediation cards fetched.")

@router.get("/active-remediations")
def get_active_remediations(db: Session = Depends(get_db)):
    actions = db.query(ResponseAction).join(RunbookStep).filter(
        RunbookStep.action_type.ilike('%auto%'),
        ResponseAction.status.in_(["In Progress", "Completed"])
    ).all()

    result = []
    for action in actions:
        runbook = action.runbook
        step = action.step
        steps_total = len(runbook.runbook_steps)
        current_step_number = step.step_number if step else 0
        progress = round((current_step_number / steps_total) * 100, 2) if steps_total else 0

        affected_system = (
            action.incident.source.name if action.incident and action.incident.source else "Unknown"
        )

        result.append({
            "title": runbook.name,
            "rule_id": str(runbook.runbook_id),
            "started_at": safe_iso(action.started_at),
            "status": action.status,
            "progress": progress,
            "current_step": step.description if step else "N/A",
            "estimated_completion": safe_iso(action.completed_at),
            "affected_system": affected_system
        })

    return success_response(result, "Active Auto Remediations fetched.")

@router.get("/auto-remediation/history")
def get_auto_remediation_history(db: Session = Depends(get_db)):
    actions = db.query(ResponseAction).join(RunbookStep).filter(
        RunbookStep.action_type.ilike('%auto%')
    ).order_by(ResponseAction.started_at.desc()).all()

    result = []
    for action in actions:
        runbook = action.runbook
        incident = action.incident
        source = incident.source.name if incident and incident.source else "Unknown"

        result.append({
            "rule": runbook.name if runbook else "Unknown",
            "trigger_time": action.started_at.isoformat() if action.started_at else None,
            "duration": format_duration(action.started_at, action.completed_at),
            "status": action.status,
            "affected_systems": source,
            "action": ResponseActionRead.from_orm(action).model_dump(mode="json")  
        })

    return success_response(result, "Auto Remediation History fetched.")