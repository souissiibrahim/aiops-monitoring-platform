from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.v1.schemas.telemetry_source import (
    TelemetrySourceInDB,
    TelemetrySourceCreate,
    TelemetrySourceUpdate,
)
from app.db.models.telemetry_source import TelemetrySource
from app.db.repositories.telemetry_source_repository import TelemetrySourceRepository
from app.services.elasticsearch.telemetry_source_service import index_telemetry_source
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    sources = TelemetrySourceRepository(db, redis).get_all()
    return success_response(serialize(sources, TelemetrySourceInDB), "Telemetry sources fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    sources = TelemetrySourceRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(sources, TelemetrySourceInDB), "Deleted telemetry sources fetched successfully.")


@router.get("/{source_id}")
def get_by_id(source_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    source = TelemetrySourceRepository(db, redis).get_by_id(source_id)
    if not source:
        return error_response("Telemetry source not found", 404)
    return success_response(serialize(source, TelemetrySourceInDB), "Telemetry source fetched successfully.")


@router.post("/")
def create(data: TelemetrySourceCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    source = TelemetrySourceRepository(db, redis).create(data.dict())
    index_telemetry_source(source)
    return success_response(serialize(source, TelemetrySourceInDB), "Telemetry source created successfully.", 201)


@router.put("/{source_id}")
def update(source_id: UUID, data: TelemetrySourceUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    updated = TelemetrySourceRepository(db, redis).update(source_id, data.dict(exclude_unset=True))
    if not updated:
        return error_response("Telemetry source not found", 404)
    db.refresh(updated)
    index_telemetry_source(updated)
    return success_response(serialize(updated, TelemetrySourceInDB), "Telemetry source updated successfully.")


@router.delete("/soft/{source_id}")
def soft_delete(source_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TelemetrySourceRepository(db, redis).soft_delete(source_id)
    if not result:
        return error_response("Telemetry source not found", 404)
    return success_response(serialize(result, TelemetrySourceInDB), "Telemetry source soft-deleted successfully.")


@router.put("/restore/{source_id}")
def restore(source_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TelemetrySourceRepository(db, redis).restore(source_id)
    if not result:
        return error_response("Telemetry source not found", 404)
    return success_response(serialize(result, TelemetrySourceInDB), "Telemetry source restored successfully.")


@router.delete("/hard/{source_id}")
def hard_delete(source_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TelemetrySourceRepository(db, redis).hard_delete(source_id)
    if not result:
        return error_response("Telemetry source not found", 404)
    return success_response(serialize(result, TelemetrySourceInDB), "Telemetry source permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = TelemetrySourceRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, TelemetrySourceInDB), f"Search results for '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    sources = db.query(TelemetrySource).filter_by(is_deleted=False).all()
    for source in sources:
        index_telemetry_source(source)
    return success_response({"count": len(sources)}, "Telemetry sources indexed to Elasticsearch.")
