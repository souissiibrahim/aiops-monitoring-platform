from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.incident_status import IncidentStatusCreate, IncidentStatusRead
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.incident_status_repository import IncidentStatusRepository
from app.db.models.incident_status import IncidentStatus
from app.services.elasticsearch.incident_status_service import index_incident_status

router = APIRouter()

@router.get("/", response_model=list[IncidentStatusRead])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return IncidentStatusRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[IncidentStatusRead])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return IncidentStatusRepository(db, redis).get_all_soft_deleted()

@router.get("/{status_id}", response_model=IncidentStatusRead)
def get_by_id(status_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    status = IncidentStatusRepository(db, redis).get_by_id(status_id)
    if not status:
        raise HTTPException(status_code=404, detail="Incident status not found")
    return status

@router.post("/", response_model=IncidentStatusRead)
def create(data: IncidentStatusCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    status = IncidentStatusRepository(db, redis).create(data.dict())
    try:
        index_incident_status(status)
    except Exception as e:
        print(f"❌ Failed to index incident status after creation: {e}")
    return status

@router.put("/{status_id}", response_model=IncidentStatusRead)
def update(status_id: UUID, data: IncidentStatusCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentStatusRepository(db, redis).update(status_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Incident status not found")
    try:
        index_incident_status(result)
    except Exception as e:
        print(f"❌ Failed to index incident status after update: {e}")
    return result

@router.delete("/soft/{status_id}", response_model=IncidentStatusRead)
def soft_delete(status_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentStatusRepository(db, redis).soft_delete(status_id)
    if not result:
        raise HTTPException(status_code=404, detail="Incident status not found")
    return result

@router.put("/restore/{status_id}", response_model=IncidentStatusRead)
def restore(status_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentStatusRepository(db, redis).restore(status_id)
    if not result:
        raise HTTPException(status_code=404, detail="Incident status not found")
    return result

@router.delete("/hard/{status_id}", response_model=IncidentStatusRead)
def hard_delete(status_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentStatusRepository(db, redis).hard_delete(status_id)
    if not result:
        raise HTTPException(status_code=404, detail="Incident status not found")
    return result

@router.get("/search/{keyword}", response_model=list[IncidentStatusRead])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return IncidentStatusRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    statuses = db.query(IncidentStatus).filter_by(is_deleted=False).all()
    for status in statuses:
        index_incident_status(status)
    return {"message": f"{len(statuses)} incident statuses indexed to Elasticsearch"}
