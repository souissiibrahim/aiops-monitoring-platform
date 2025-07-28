from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.incident import IncidentCreate, IncidentRead
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.incident_repository import IncidentRepository
from app.db.models.incident import Incident
from app.services.elasticsearch.incident_service import index_incident
from app.utils.response import success_response, error_response
from sqlalchemy import func
from app.db.models.severity_level import SeverityLevel
from app.db.models.incident_status import IncidentStatus

router = APIRouter()

def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")

@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    incidents = IncidentRepository(db, redis).get_all()
    return success_response(serialize(incidents, IncidentRead), "Incidents fetched successfully.")

@router.get("/count")
def get_total_incidents(db: Session = Depends(get_db)):
    total = db.query(func.count(Incident.incident_id)).filter(Incident.is_deleted == False).scalar()
    return success_response({"total_incidents": total}, "Total incidents fetched.")

@router.get("/count/critical")
def get_critical_incidents(db: Session = Depends(get_db)):
    critical = db.query(SeverityLevel).filter(SeverityLevel.name == "Critical").first()
    if not critical:
        return success_response({"count": 0}, "No severity level named 'Critical' found.")

    count = db.query(func.count(Incident.incident_id)).filter(
        Incident.severity_level_id == critical.severity_level_id,
        Incident.is_deleted == False
    ).scalar()

    return success_response({"critical_count": count}, "Critical incidents counted.")

@router.get("/count/high-severity")
def get_high_severity_incidents(db: Session = Depends(get_db)):
    high_severity = db.query(SeverityLevel).filter_by(name="High").first()

    if not high_severity:
        return success_response({"high_severity_incidents": 0}, "No 'High' severity level defined.")

    count = db.query(func.count(Incident.incident_id))\
        .filter(Incident.severity_level_id == high_severity.severity_level_id)\
        .filter(Incident.is_deleted == False).scalar()

    return success_response({"high_severity_incidents": count}, "High severity incidents counted.")

@router.get("/count/open")
def get_open_incidents_count(db: Session = Depends(get_db)):
    open_status = db.query(IncidentStatus).filter(IncidentStatus.name == "Open").first()

    if not open_status:
        return error_response("Status 'Open' not found", 404)

    count = db.query(func.count(Incident.incident_id)).filter(
        Incident.status_id == open_status.status_id,
        Incident.is_deleted == False
    ).scalar()

    return success_response({"open_incident_count": count}, "Open incidents count fetched successfully.")

@router.get("/count/investigating")
def get_investigating_incidents_count(db: Session = Depends(get_db)):
    investigating_status = db.query(IncidentStatus).filter(IncidentStatus.name == "Investigating").first()
    if not investigating_status:
        return error_response("Investigating status not found", 404)

    count = db.query(func.count(Incident.incident_id)).filter(
        Incident.status_id == investigating_status.status_id,
        Incident.is_deleted == False
    ).scalar()

    return success_response({"count": count}, "Investigating incidents count fetched.")


@router.get("/active")
def get_active_incidents(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    incidents = db.query(Incident).filter(Incident.is_deleted == False).all()
    
    response = []
    for inc in incidents:
        response.append({
            "id": str(inc.incident_id),
            "title": inc.title,
            "severity": inc.severity_level.name if inc.severity_level else None,
            "status": inc.status.name if inc.status else None,
            "created_at": inc.created_at.strftime("%Y-%m-%d %H:%M") if inc.created_at else None
        })
    
    return success_response(response, "Active incidents listed.")



@router.get("/by-severity/{level}")
def get_incidents_by_severity(level: str, db: Session = Depends(get_db)):
    level_normalized = level.capitalize()
    severity = db.query(SeverityLevel).filter(SeverityLevel.name == level_normalized).first()

    if not severity:
        return error_response(f"Severity level '{level}' not found.", 404)

    incidents = db.query(Incident).filter(
        Incident.severity_level_id == severity.severity_level_id,
        Incident.is_deleted == False
    ).all()

    response = []
    for inc in incidents:
        response.append({
            "id": str(inc.incident_id),
            "title": inc.title,
            "severity": inc.severity_level.name if inc.severity_level else None,
            "status": inc.status.name if inc.status else None,
            "created_at": inc.created_at.strftime("%Y-%m-%d %H:%M") if inc.created_at else None
        })

    return success_response(response, f"{level_normalized} severity incidents listed.")

@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    incidents = IncidentRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(incidents, IncidentRead), "Soft deleted incidents fetched successfully.")


@router.get("/{incident_id}")
def get_by_id(incident_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    incident = IncidentRepository(db, redis).get_by_id(incident_id)
    if not incident:
        return error_response("Incident not found", 404)
    return success_response(serialize(incident, IncidentRead), "Incident fetched successfully.")


@router.post("/")
def create(data: IncidentCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    incident = IncidentRepository(db, redis).create(data.dict())
    index_incident(incident)
    return success_response(serialize(incident, IncidentRead), "Incident created successfully.", 201)


@router.put("/{incident_id}")
def update(incident_id: UUID, data: IncidentCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentRepository(db, redis).update(incident_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Incident not found", 404)

    db.refresh(result)
    index_incident(result)
    return success_response(serialize(result, IncidentRead), "Incident updated successfully.")


@router.delete("/soft/{incident_id}")
def soft_delete(incident_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentRepository(db, redis).soft_delete(incident_id)
    if not result:
        return error_response("Incident not found", 404)
    return success_response(serialize(result, IncidentRead), "Incident soft deleted successfully.")


@router.put("/restore/{incident_id}")
def restore(incident_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentRepository(db, redis).restore(incident_id)
    if not result:
        return error_response("Incident not found", 404)
    return success_response(serialize(result, IncidentRead), "Incident restored successfully.")


@router.delete("/hard/{incident_id}")
def hard_delete(incident_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentRepository(db, redis).hard_delete(incident_id)
    if not result:
        return error_response("Incident not found", 404)
    return success_response(serialize(result, IncidentRead), "Incident permanently deleted successfully.")



"""@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = IncidentRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, IncidentRead), f"Search results for keyword '{keyword}'.")"""


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = IncidentRepository(db, redis).search(keyword, es)

    response = []
    for inc in results:
        response.append({
            "id": str(inc.incident_id),
            "title": inc.title,
            "severity": inc.severity_level.name if inc.severity_level else None,
            "status": inc.status.name if inc.status else None,
            "created_at": inc.created_at.strftime("%Y-%m-%d %H:%M") if inc.created_at else None
        })

    return success_response(response, f"Search results for keyword '{keyword}'.")

    
@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    incidents = db.query(Incident).filter_by(is_deleted=False).all()
    for incident in incidents:
        index_incident(incident)
    return success_response({"count": len(incidents)}, "All incidents indexed to Elasticsearch.")
