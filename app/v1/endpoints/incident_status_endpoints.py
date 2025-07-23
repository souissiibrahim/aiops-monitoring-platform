from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.incident_status import IncidentStatusCreate, IncidentStatusRead
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.incident_status_repository import IncidentStatusRepository
from app.db.models.incident_status import IncidentStatus
from app.services.elasticsearch.incident_status_service import index_incident_status
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    statuses = IncidentStatusRepository(db, redis).get_all()
    return success_response(serialize(statuses, IncidentStatusRead), "Incident statuses fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    statuses = IncidentStatusRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(statuses, IncidentStatusRead), "Deleted incident statuses fetched successfully.")


@router.get("/{status_id}")
def get_by_id(status_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    status = IncidentStatusRepository(db, redis).get_by_id(status_id)
    if not status:
        return error_response("Incident status not found", 404)
    return success_response(serialize(status, IncidentStatusRead), "Incident status fetched successfully.")


@router.post("/")
def create(data: IncidentStatusCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    status = IncidentStatusRepository(db, redis).create(data.dict())
    try:
        index_incident_status(status)
    except Exception as e:
        print(f"❌ Failed to index incident status after creation: {e}")
    return success_response(serialize(status, IncidentStatusRead), "Incident status created successfully.", 201)


@router.put("/{status_id}")
def update(status_id: UUID, data: IncidentStatusCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentStatusRepository(db, redis).update(status_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Incident status not found", 404)
    try:
        index_incident_status(result)
    except Exception as e:
        print(f"❌ Failed to index incident status after update: {e}")
    return success_response(serialize(result, IncidentStatusRead), "Incident status updated successfully.")


@router.delete("/soft/{status_id}")
def soft_delete(status_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentStatusRepository(db, redis).soft_delete(status_id)
    if not result:
        return error_response("Incident status not found", 404)
    return success_response(serialize(result, IncidentStatusRead), "Incident status soft deleted.")


@router.put("/restore/{status_id}")
def restore(status_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentStatusRepository(db, redis).restore(status_id)
    if not result:
        return error_response("Incident status not found", 404)
    return success_response(serialize(result, IncidentStatusRead), "Incident status restored.")


@router.delete("/hard/{status_id}")
def hard_delete(status_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentStatusRepository(db, redis).hard_delete(status_id)
    if not result:
        return error_response("Incident status not found", 404)
    return success_response(serialize(result, IncidentStatusRead), "Incident status permanently deleted.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    try:
        results = IncidentStatusRepository(db, redis).search(keyword, es)
        return success_response(serialize(results, IncidentStatusRead), f"Search results for '{keyword}'.")
    except Exception as e:
        print(f"[Elasticsearch ERROR] {e}")
        return error_response("Search temporarily unavailable", 503)


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    statuses = db.query(IncidentStatus).filter_by(is_deleted=False).all()
    for status in statuses:
        try:
            index_incident_status(status)
        except Exception as e:
            print(f"❌ Failed to index incident status {status.incident_status_id}: {e}")
    return success_response({"count": len(statuses)}, "All incident statuses indexed to Elasticsearch.")
