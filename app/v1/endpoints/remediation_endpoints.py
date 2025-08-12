from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models.response_action import ResponseAction
from app.db.models.runbook import Runbook
from app.db.models.incident import Incident
from app.services.remediation_orchestrator import run_auto_remediation

router = APIRouter(prefix="/remediation", tags=["Remediation"])

class ApproveBody(BaseModel):
    action_id: str

@router.post("/approve")
def approve_remediation(body: ApproveBody, db: Session = Depends(get_db)):
    ra = db.query(ResponseAction).get(body.action_id)
    if not ra: raise HTTPException(404, "ResponseAction not found")
    if ra.status != "Pending": raise HTTPException(400, f"Expected Pending, got {ra.status}")

    incident = db.query(Incident).get(ra.incident_id)
    runbook = db.query(Runbook).get(ra.runbook_id)
    if not incident or not runbook:
        raise HTTPException(404, "Incident or Runbook missing")

    result = run_auto_remediation(
        incident_id=str(incident.incident_id),
        job={"job_id": str(runbook.runbook_id), "name": runbook.name, "description": runbook.description},
        argstring=f"-incident_id {incident.incident_id}"
    )
    return {"ok": True, "result": result}
