import time
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models.response_action import ResponseAction
from app.db.models.runbook import Runbook
from app.db.models.incident import Incident
from app.services.elasticsearch.response_action_service import index_response_action  # if available
from app.services.elasticsearch.incident_service import index_incident  # if available
from Rundeck.rundeck_client import trigger_rundeck_job, get_execution  # ensure get_execution exists
from app.utils.slack_notifier import send_to_slack  # optional

IDEMP_WINDOW_MIN = 15
POLL_INTERVAL_SEC = 4
MAX_POLL_MIN = 10

def _utcnow():
    return datetime.now(timezone.utc)

def _idempotent_recent(db: Session, incident_id, runbook_id) -> Optional[ResponseAction]:
    cutoff = _utcnow() - timedelta(minutes=IDEMP_WINDOW_MIN)
    return (
        db.query(ResponseAction)
          .filter(ResponseAction.incident_id == incident_id,
                  ResponseAction.runbook_id == runbook_id,
                  ResponseAction.started_at >= cutoff)
          .order_by(ResponseAction.started_at.desc())
          .first()
    )

def _upsert_runbook(db: Session, job: Dict[str, Any]) -> Runbook:
    # You’re using Rundeck job UUID as runbook_id, perfect.
    rb = db.query(Runbook).get(job["job_id"])
    if not rb:
        rb = Runbook(
            runbook_id=job["job_id"],
            name=job.get("name", "Unnamed"),
            description=job.get("description", ""),
            priority=job.get("priority") or 5
        )
        db.add(rb)
        db.flush()
    return rb

def _flip_incident_status(db: Session, incident: Incident, name: str):
    # Your incidents table uses status_id FK. If you’re storing the *name* in a field,
    # adjust this to resolve name → status_id via `incident_statuses` lookup.
    incident.status_id = incident.status_id  # keep if you already set; else look up by name if needed.
    incident.updated_at = _utcnow()
    db.add(incident)
    try:
        index_incident(incident)
    except Exception:
        pass

def _index_ra(ra: ResponseAction):
    try:
        index_response_action(ra)
    except Exception:
        pass

def create_pending_action(db: Session, *, incident: Incident, runbook: Runbook, reason: Optional[str]) -> ResponseAction:
    ra = ResponseAction(
        action_id=uuid4(),
        incident_id=incident.incident_id,
        runbook_id=runbook.runbook_id,
        status="Pending",
        execution_log=reason or "",
        started_at=None,
        completed_at=None,
        error_message=None
    )
    db.add(ra)
    db.flush()
    _index_ra(ra)
    return ra

def run_auto_remediation(*, incident_id: str, job: Dict[str, Any], argstring: str, human_reason_if_skip: Optional[str] = None) -> Dict[str, Any]:
    with SessionLocal() as db:
        incident = db.query(Incident).get(incident_id)
        if not incident:
            return {"ok": False, "error": f"Incident {incident_id} not found"}

        runbook = _upsert_runbook(db, job)

        # If we're not authorized to auto-run, create Pending + notify
        if human_reason_if_skip:
            ra = create_pending_action(db, incident=incident, runbook=runbook, reason=human_reason_if_skip)
            try:
                send_to_slack(f"🧑‍⚖️ Pending remediation for incident `{incident_id}` → `{runbook.name}`. Reason: {human_reason_if_skip}\nAction ID: {ra.action_id}")
            except Exception:
                pass
            db.commit()
            return {"ok": True, "auto": False, "status": "pending", "response_action_id": str(ra.action_id)}

        # Idempotency check
        recent = _idempotent_recent(db, incident.incident_id, runbook.runbook_id)
        if recent:
            return {"ok": True, "idempotent": True, "response_action_id": str(recent.action_id), "message": "recent remediation exists"}

        # In Progress action
        ra = ResponseAction(
            action_id=uuid4(),
            incident_id=incident.incident_id,
            runbook_id=runbook.runbook_id,
            status="In Progress",
            started_at=_utcnow()
        )
        db.add(ra)
        db.flush()
        _index_ra(ra)

        # Flip incident to Mitigating (if you track via name→id, map here)
        _flip_incident_status(db, incident, "Mitigating")
        db.commit()

        # Trigger Rundeck
        try:
            exec_payload = trigger_rundeck_job(job["job_id"], argstring=argstring)
            execution_id = exec_payload.get("id")
        except Exception as e:
            ra.status = "Failed"
            ra.error_message = f"Trigger error: {e}"
            ra.completed_at = _utcnow()
            db.add(ra); db.commit(); _index_ra(ra)
            _flip_incident_status(db, incident, "Investigating"); db.commit()
            try: send_to_slack(f"❌ Rundeck trigger failed for incident `{incident_id}`: {e}")
            except Exception: pass
            return {"ok": False, "error": str(e)}

        # Poll to completion
        deadline = _utcnow() + timedelta(minutes=MAX_POLL_MIN)
        exec_status = "running"
        logs_accum = []
        while _utcnow() < deadline:
            try:
                info = get_execution(execution_id)
                exec_status = info.get("status", exec_status)  # running/succeeded/failed/aborted
                if exec_status in ("succeeded", "failed", "aborted"):
                    break
            except Exception as e:
                logs_accum.append(f"poll_error: {e}")
                break
            time.sleep(POLL_INTERVAL_SEC)

        ra.completed_at = _utcnow()
        if logs_accum:
            ra.execution_log = (ra.execution_log or "") + "\n".join(logs_accum)

        if exec_status == "succeeded":
            ra.status = "Completed"
            db.add(ra); db.commit(); _index_ra(ra)
            _flip_incident_status(db, incident, "Resolved"); db.commit()
            try: send_to_slack(f"✅ Remediation succeeded for incident `{incident_id}` (job `{runbook.name}`)")
            except Exception: pass
            return {"ok": True, "status": "succeeded", "execution_id": execution_id, "response_action_id": str(ra.action_id)}
        else:
            ra.status = "Failed"
            db.add(ra); db.commit(); _index_ra(ra)
            _flip_incident_status(db, incident, "Investigating"); db.commit()
            try: send_to_slack(f"❌ Remediation failed for incident `{incident_id}` (job `{runbook.name}`): {exec_status}")
            except Exception: pass
            return {"ok": False, "status": exec_status, "execution_id": execution_id, "response_action_id": str(ra.action_id)}
