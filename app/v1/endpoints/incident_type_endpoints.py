from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.incident_type import IncidentTypeCreate, IncidentTypeRead
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.incident_type_repository import IncidentTypeRepository
from app.db.models.incident_type import IncidentType
from app.services.elasticsearch.incident_type_service import index_incident_type
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    items = IncidentTypeRepository(db, redis).get_all()
    return success_response(serialize(items, IncidentTypeRead), "Incident types fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    items = IncidentTypeRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(items, IncidentTypeRead), "Deleted incident types fetched successfully.")


@router.get("/{incident_type_id}")
def get_by_id(incident_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    incident_type = IncidentTypeRepository(db, redis).get_by_id(incident_type_id)
    if not incident_type:
        return error_response("Incident type not found", 404)
    return success_response(serialize(incident_type, IncidentTypeRead), "Incident type fetched successfully.")


@router.post("/")
def create(data: IncidentTypeCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    incident_type = IncidentTypeRepository(db, redis).create(data.dict())
    try:
        index_incident_type(incident_type)
    except Exception as e:
        print(f"❌ Failed to index incident type after creation: {e}")
    return success_response(serialize(incident_type, IncidentTypeRead), "Incident type created successfully.", 201)


@router.put("/{incident_type_id}")
def update(incident_type_id: UUID, data: IncidentTypeCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentTypeRepository(db, redis).update(incident_type_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Incident type not found", 404)
    try:
        index_incident_type(result)
    except Exception as e:
        print(f"❌ Failed to index incident type after update: {e}")
    return success_response(serialize(result, IncidentTypeRead), "Incident type updated successfully.")


@router.delete("/soft/{incident_type_id}")
def soft_delete(incident_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentTypeRepository(db, redis).soft_delete(incident_type_id)
    if not result:
        return error_response("Incident type not found", 404)
    return success_response(serialize(result, IncidentTypeRead), "Incident type soft deleted.")


@router.put("/restore/{incident_type_id}")
def restore(incident_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentTypeRepository(db, redis).restore(incident_type_id)
    if not result:
        return error_response("Incident type not found", 404)
    return success_response(serialize(result, IncidentTypeRead), "Incident type restored.")


@router.delete("/hard/{incident_type_id}")
def hard_delete(incident_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentTypeRepository(db, redis).hard_delete(incident_type_id)
    if not result:
        return error_response("Incident type not found", 404)
    return success_response(serialize(result, IncidentTypeRead), "Incident type permanently deleted.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    try:
        results = IncidentTypeRepository(db, redis).search(keyword, es)
        return success_response(serialize(results, IncidentTypeRead), f"Search results for keyword '{keyword}'.")
    except Exception as e:
        print(f"[Elasticsearch ERROR] {e}")
        return error_response("Search temporarily unavailable", 503)


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    incident_types = db.query(IncidentType).filter_by(is_deleted=False).all()
    for incident_type in incident_types:
        try:
            index_incident_type(incident_type)
        except Exception as e:
            print(f"❌ Indexing error for incident_type {incident_type.incident_type_id}: {e}")
    return success_response({"count": len(incident_types)}, "All incident types indexed to Elasticsearch.")
