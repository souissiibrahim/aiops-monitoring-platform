from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.incident_type import IncidentTypeCreate, IncidentTypeRead
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.incident_type_repository import IncidentTypeRepository
from app.db.models.incident_type import IncidentType
from app.services.elasticsearch.incident_type_service import index_incident_type

router = APIRouter()

@router.get("/", response_model=list[IncidentTypeRead])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return IncidentTypeRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[IncidentTypeRead])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return IncidentTypeRepository(db, redis).get_all_soft_deleted()

@router.get("/{incident_type_id}", response_model=IncidentTypeRead)
def get_by_id(incident_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    incident_type = IncidentTypeRepository(db, redis).get_by_id(incident_type_id)
    if not incident_type:
        raise HTTPException(status_code=404, detail="Incident type not found")
    return incident_type

@router.post("/", response_model=IncidentTypeRead)
def create(data: IncidentTypeCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    incident_type = IncidentTypeRepository(db, redis).create(data.dict())
    try:
        index_incident_type(incident_type)
    except Exception as e:
        print(f"❌ Failed to index incident type after creation: {e}")
    return incident_type

@router.put("/{incident_type_id}", response_model=IncidentTypeRead)
def update(incident_type_id: UUID, data: IncidentTypeCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentTypeRepository(db, redis).update(incident_type_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Incident type not found")
    try:
        index_incident_type(result)
    except Exception as e:
        print(f"❌ Failed to index incident type after update: {e}")
    return result

@router.delete("/soft/{incident_type_id}", response_model=IncidentTypeRead)
def soft_delete(incident_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentTypeRepository(db, redis).soft_delete(incident_type_id)
    if not result:
        raise HTTPException(status_code=404, detail="Incident type not found")
    return result

@router.put("/restore/{incident_type_id}", response_model=IncidentTypeRead)
def restore(incident_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentTypeRepository(db, redis).restore(incident_type_id)
    if not result:
        raise HTTPException(status_code=404, detail="Incident type not found")
    return result

@router.delete("/hard/{incident_type_id}", response_model=IncidentTypeRead)
def hard_delete(incident_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentTypeRepository(db, redis).hard_delete(incident_type_id)
    if not result:
        raise HTTPException(status_code=404, detail="Incident type not found")
    return result

@router.get("/search/{keyword}", response_model=list[IncidentTypeRead])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return IncidentTypeRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    incident_types = db.query(IncidentType).filter_by(is_deleted=False).all()
    for incident_type in incident_types:
        index_incident_type(incident_type)
    return {"message": f"{len(incident_types)} incident types indexed to Elasticsearch"}
