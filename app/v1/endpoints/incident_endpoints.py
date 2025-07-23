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

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    incidents = IncidentRepository(db, redis).get_all()
    return success_response(serialize(incidents, IncidentRead), "Incidents fetched successfully.")


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


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = IncidentRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, IncidentRead), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    incidents = db.query(Incident).filter_by(is_deleted=False).all()
    for incident in incidents:
        index_incident(incident)
    return success_response({"count": len(incidents)}, "All incidents indexed to Elasticsearch.")
