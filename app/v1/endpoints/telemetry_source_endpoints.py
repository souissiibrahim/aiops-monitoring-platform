from fastapi import APIRouter, Depends, HTTPException
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

router = APIRouter()


@router.get("/", response_model=list[TelemetrySourceInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return TelemetrySourceRepository(db, redis).get_all()


@router.get("/deleted", response_model=list[TelemetrySourceInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return TelemetrySourceRepository(db, redis).get_all_soft_deleted()


@router.get("/{source_id}", response_model=TelemetrySourceInDB)
def get_by_id(source_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    source = TelemetrySourceRepository(db, redis).get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Telemetry source not found")
    return source


@router.post("/", response_model=TelemetrySourceInDB)
def create(data: TelemetrySourceCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    source = TelemetrySourceRepository(db, redis).create(data.dict())
    index_telemetry_source(source)
    return source


@router.put("/{source_id}", response_model=TelemetrySourceInDB)
def update(source_id: UUID, data: TelemetrySourceUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    updated = TelemetrySourceRepository(db, redis).update(source_id, data.dict(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Telemetry source not found")
    db.refresh(updated)
    index_telemetry_source(updated)
    return updated


@router.delete("/soft/{source_id}", response_model=TelemetrySourceInDB)
def soft_delete(source_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TelemetrySourceRepository(db, redis).soft_delete(source_id)
    if not result:
        raise HTTPException(status_code=404, detail="Telemetry source not found")
    return result


@router.put("/restore/{source_id}", response_model=TelemetrySourceInDB)
def restore(source_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TelemetrySourceRepository(db, redis).restore(source_id)
    if not result:
        raise HTTPException(status_code=404, detail="Telemetry source not found")
    return result


@router.delete("/hard/{source_id}", response_model=TelemetrySourceInDB)
def hard_delete(source_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TelemetrySourceRepository(db, redis).hard_delete(source_id)
    if not result:
        raise HTTPException(status_code=404, detail="Telemetry source not found")
    return result


@router.get("/search/{keyword}", response_model=list[TelemetrySourceInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return TelemetrySourceRepository(db, redis).search(keyword, es)


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    sources = db.query(TelemetrySource).filter_by(is_deleted=False).all()
    for source in sources:
        index_telemetry_source(source)
    return {"message": f"{len(sources)} telemetry sources indexed to Elasticsearch"}
