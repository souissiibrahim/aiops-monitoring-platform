import os
import time
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import requests
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models.response_action import ResponseAction
from app.db.models.runbook import Runbook
from app.db.models.runbook_step import RunbookStep
from app.db.models.incident import Incident
from app.db.models.incident_status import IncidentStatus
from app.services.elasticsearch.response_action_service import index_response_action
from app.services.elasticsearch.incident_service import index_incident
from Rundeck.rundeck_client import trigger_rundeck_job, get_execution
from app.utils.slack_notifier import send_to_slack

# --------------------------
# Config
# --------------------------
IDEMP_WINDOW_MIN = 0
POLL_INTERVAL_SEC = 3
MAX_POLL_MIN = 10

RUNDECK_BASE_URL = os.getenv("RUNDECK_BASE_URL", "http://localhost:4440")
RUNDECK_API_VERSION = os.getenv("RUNDECK_API_VERSION", "40")
RUNDECK_API_TOKEN = os.getenv("RUNDECK_API_TOKEN", "")

_HEADERS = {
    "X-Rundeck-Auth-Token": RUNDECK_API_TOKEN,
    "Accept": "application/json",
}

_STATUS_CACHE = {}

STATUS_ALIASES = {
    "open": ["open", "opened"],
    "investigating": ["investigating", "investigation", "progress", "in progress"],
    "resolved": ["resolved"],
    "closed": ["closed"]
}

# --------------------------
# Helpers
# --------------------------
def _utcnow():
    return datetime.now(timezone.utc)


"""def _status_id(db: Session, name: str):
    key = name.lower()
    if key in _STATUS_CACHE:
        return _STATUS_CACHE[key]
    row = db.query(IncidentStatus).filter(IncidentStatus.name == name).first()
    if row:
        _STATUS_CACHE[key] = row.status_id
        return row.status_id
    return None """

def _status_id(db: Session, target: str):
    names = [target] + STATUS_ALIASES.get(target.lower(), [])
    q = db.query(IncidentStatus).filter(IncidentStatus.name.in_(names))
    row = q.first()
    return row.status_id if row else None


def _flip_incident_status(db: Session, incident: Incident, name: str):
    sid = _status_id(db, name)
    if sid:
        incident.status_id = sid
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


def _idempotent_recent(db: Session, incident_id, runbook_id) -> Optional[ResponseAction]:
    cutoff = _utcnow() - timedelta(minutes=IDEMP_WINDOW_MIN)
    return (
        db.query(ResponseAction)
        .filter(
            ResponseAction.incident_id == incident_id,
            ResponseAction.runbook_id == runbook_id,
            ResponseAction.started_at >= cutoff,
        )
        .order_by(ResponseAction.started_at.desc())
        .first()
    )


def _upsert_runbook(db: Session, job: Dict[str, Any]) -> Runbook:
    rb = db.query(Runbook).get(job["job_id"])
    if not rb:
        rb = Runbook(
            runbook_id=job["job_id"],
            name=job.get("name", "Unnamed"),
            description=job.get("description", ""),
            priority=job.get("priority") or 5,
        )
        db.add(rb)
        db.flush()
    return rb


def _rd_get(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    url = f"{RUNDECK_BASE_URL}/api/{RUNDECK_API_VERSION}{path}"
    r = requests.get(url, headers=_HEADERS, params=params or {}, timeout=20)
    r.raise_for_status()
    return r.json()


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def _rundeck_state_to_status(s: Optional[str]) -> str:
    s = (s or "").lower()
    if s in ("running", "in_progress", "node-partial"):
        return "In Progress"
    if s in ("succeeded", "success", "completed"):
        return "Completed"
    if s in ("failed", "aborted", "timedout", "timeout"):
        return "Failed"
    return "In Progress"


def _get_execution_state(exec_id: int) -> Dict[str, Any]:
    return _rd_get(f"/execution/{exec_id}/state")


def _get_step_logs(exec_id: int, stepctx: str, lastlines: int = 50) -> List[str]:
    data = _rd_get(
        f"/execution/{exec_id}/output/step/{stepctx}",
        params={"format": "json", "lastlines": lastlines},
    )
    entries = data.get("entries", []) or []
    return [e["log"] for e in entries if e.get("log")]


def _flatten_steps(steps: List[Dict[str, Any]], parent_ctx: Optional[str] = None):
    for s in steps or []:
        sid = str(s.get("id"))
        stepctx = f"{parent_ctx}/{sid}" if parent_ctx else sid
        yield stepctx, s
        wf = s.get("workflow")
        if wf and isinstance(wf, dict):
            yield from _flatten_steps(wf.get("steps", []), stepctx)


def _load_step_map(db: Session, runbook_id) -> Dict[str, str]:
    rows = (
        db.query(RunbookStep)
        .filter(RunbookStep.runbook_id == runbook_id)
        .all()
    )
    return {str(r.step_number): str(r.step_id) for r in rows}


def _upsert_step_response_action(
    db: Session,
    *,
    incident_id,
    runbook_id,
    step_id,
    rundeck_step_ctx,
    status: str,
    started_at: Optional[datetime],
    completed_at: Optional[datetime],
    logs_snippet: Optional[str],
    parent_action_id: Optional[str],
) -> ResponseAction:
    ra = (
        db.query(ResponseAction)
        .filter(
            ResponseAction.incident_id == incident_id,
            ResponseAction.runbook_id == runbook_id,
            ResponseAction.step_id == step_id,
        )
        .one_or_none()
    )
    if ra is None:
        ra = ResponseAction(
            action_id=uuid4(),
            incident_id=incident_id,
            runbook_id=runbook_id,
            step_id=step_id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            execution_log=logs_snippet or "",
        )
        if parent_action_id and hasattr(ra, "parent_action_id"):
            ra.parent_action_id = parent_action_id
        db.add(ra)
    else:
        ra.status = status or ra.status
        ra.started_at = started_at or ra.started_at
        ra.completed_at = completed_at or ra.completed_at
        if logs_snippet:
            ra.execution_log = (ra.execution_log or "") + "\n" + logs_snippet

    db.flush()
    _index_ra(ra)
    return ra


# --------------------------
# Core functions
# --------------------------
def create_pending_action(db: Session, *, incident: Incident, runbook: Runbook, reason: Optional[str]) -> ResponseAction:
    ra = ResponseAction(
        action_id=uuid4(),
        incident_id=incident.incident_id,
        runbook_id=runbook.runbook_id,
        status="Pending",
        execution_log=reason or "",
    )
    db.add(ra)
    db.flush()
    _index_ra(ra)
    return ra


def _follow_rundeck_execution_per_step(
    db: Session,
    *,
    exec_id: int,
    runbook_id,
    incident_id,
    parent_response_action_id: Optional[str],
):
    step_map = _load_step_map(db, runbook_id)
    seen_done: set[str] = set()
    deadline = _utcnow() + timedelta(minutes=MAX_POLL_MIN)

    while _utcnow() < deadline:
        try:
            state = _get_execution_state(exec_id)
        except Exception:
            break

        steps = state.get("steps") or []
        for stepctx, s in _flatten_steps(steps):
            step_number = stepctx.split("/")[-1]
            db_step_id = step_map.get(step_number)
            if not db_step_id:
                continue

            status = _rundeck_state_to_status(s.get("executionState"))
            started_at = _parse_iso(s.get("startTime"))
            completed_at = _parse_iso(s.get("endTime"))

            logs_snippet = None
            if status == "In Progress" or (completed_at and stepctx not in seen_done):
                try:
                    last_lines = _get_step_logs(exec_id, stepctx, lastlines=50)
                    if last_lines:
                        logs_snippet = "\n".join(last_lines[-20:])
                except Exception:
                    pass

            _upsert_step_response_action(
                db,
                incident_id=str(incident_id),
                runbook_id=str(runbook_id),
                step_id=str(db_step_id),
                rundeck_step_ctx=stepctx,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                logs_snippet=logs_snippet,
                parent_action_id=str(parent_response_action_id) if parent_response_action_id else None,
            )

            if completed_at:
                seen_done.add(stepctx)

        db.commit()

        if state.get("completed"):
            break

        time.sleep(POLL_INTERVAL_SEC)

    # Finalize incident status
    step_rows = (
        db.query(ResponseAction.status)
        .filter(
            ResponseAction.incident_id == incident_id,
            ResponseAction.runbook_id == runbook_id,
            ResponseAction.step_id.isnot(None),
        )
        .all()
    )
    statuses = {s for (s,) in step_rows}
    if statuses and statuses.issubset({"Completed"}):
        _flip_incident_status(db, db.query(Incident).get(incident_id), "Resolved")
    else:
        _flip_incident_status(db, db.query(Incident).get(incident_id), "Investigating")
    db.commit()


def run_auto_remediation(
    *,
    incident_id: str,
    job: Dict[str, Any],
    argstring: str,
    human_reason_if_skip: Optional[str] = None,
) -> Dict[str, Any]:
    with SessionLocal() as db:
        incident = db.query(Incident).get(incident_id)
        if not incident:
            return {"ok": False, "error": f"Incident {incident_id} not found"}

        runbook = _upsert_runbook(db, job)

        if human_reason_if_skip:
            ra = create_pending_action(db, incident=incident, runbook=runbook, reason=human_reason_if_skip)
            try:
                send_to_slack(
                    f"🧑‍⚖️ Pending remediation for incident `{incident_id}` → `{runbook.name}`. Reason: {human_reason_if_skip}\nAction ID: {ra.action_id}"
                )
            except Exception:
                pass
            db.commit()
            return {"ok": True, "auto": False, "status": "pending", "response_action_id": str(ra.action_id)}

        recent = _idempotent_recent(db, incident.incident_id, runbook.runbook_id)
        if recent:
            return {
                "ok": True,
                "idempotent": True,
                "response_action_id": str(recent.action_id),
                "message": "recent remediation exists",
            }

        parent_ra = ResponseAction(
            action_id=uuid4(),
            incident_id=incident.incident_id,
            runbook_id=runbook.runbook_id,
            status="In Progress",
            started_at=_utcnow(),
            execution_log="Auto-remediation started.",
        )
        db.add(parent_ra)
        db.flush()
        _index_ra(parent_ra)

        _flip_incident_status(db, incident, "Investigating")
        db.commit()

        try:
            exec_payload = trigger_rundeck_job(job["job_id"], argstring=argstring)
            execution_id = exec_payload.get("id")
        except Exception as e:
            parent_ra.status = "Failed"
            parent_ra.error_message = f"Trigger error: {e}"
            parent_ra.completed_at = _utcnow()
            db.add(parent_ra)
            db.commit()
            _index_ra(parent_ra)
            _flip_incident_status(db, incident, "Investigating")
            db.commit()
            try:
                send_to_slack(f"❌ Rundeck trigger failed for incident `{incident_id}`: {e}")
            except Exception:
                pass
            return {"ok": False, "error": str(e)}

        deadline = _utcnow() + timedelta(minutes=MAX_POLL_MIN)
        overall_status = "running"
        while _utcnow() < deadline:
            try:
                info = get_execution(execution_id)
                overall_status = info.get("status", overall_status)
                if overall_status in ("succeeded", "failed", "aborted"):
                    break
            except Exception:
                break
            time.sleep(POLL_INTERVAL_SEC)

        parent_ra.completed_at = _utcnow()
        parent_ra.status = "Completed" if overall_status == "succeeded" else "Failed"
        db.add(parent_ra)
        db.commit()
        _index_ra(parent_ra)

        _follow_rundeck_execution_per_step(
            db,
            exec_id=execution_id,
            runbook_id=runbook.runbook_id,
            incident_id=incident.incident_id,
            parent_response_action_id=str(parent_ra.action_id),
        )

        try:
            if overall_status == "succeeded":
                send_to_slack(f"✅ Remediation succeeded for incident `{incident_id}` (job `{runbook.name}`)")
                return {
                    "ok": True,
                    "status": "succeeded",
                    "execution_id": execution_id,
                    "response_action_id": str(parent_ra.action_id),
                }
            else:
                send_to_slack(
                    f"❌ Remediation failed for incident `{incident_id}` (job `{runbook.name}`): {overall_status}"
                )
                return {
                    "ok": False,
                    "status": overall_status,
                    "execution_id": execution_id,
                    "response_action_id": str(parent_ra.action_id),
                }
        except Exception:
            return {
                "ok": overall_status == "succeeded",
                "status": overall_status,
                "execution_id": execution_id,
                "response_action_id": str(parent_ra.action_id),
            }
