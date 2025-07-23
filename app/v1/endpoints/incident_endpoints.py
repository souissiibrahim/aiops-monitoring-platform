from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.incident import IncidentCreate, IncidentRead
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.incident_repository import IncidentRepository
from app.db.models.incident import Incident
from app.services.elasticsearch.incident_service import index_incident

router = APIRouter()

@router.get("/", response_model=list[IncidentRead])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return IncidentRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[IncidentRead])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return IncidentRepository(db, redis).get_all_soft_deleted()

@router.get("/{incident_id}", response_model=IncidentRead)
def get_by_id(incident_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    incident = IncidentRepository(db, redis).get_by_id(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident

@router.post("/", response_model=IncidentRead)
def create(data: IncidentCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    incident = IncidentRepository(db, redis).create(data.dict())
    index_incident(incident)
    return incident

@router.put("/{incident_id}", response_model=IncidentRead)
def update(incident_id: UUID, data: IncidentCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentRepository(db, redis).update(incident_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    db.refresh(result)
    index_incident(result)
    return result

@router.delete("/soft/{incident_id}", response_model=IncidentRead)
def soft_delete(incident_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentRepository(db, redis).soft_delete(incident_id)
    if not result:
        raise HTTPException(status_code=404, detail="Incident not found")
    return result

@router.put("/restore/{incident_id}", response_model=IncidentRead)
def restore(incident_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentRepository(db, redis).restore(incident_id)
    if not result:
        raise HTTPException(status_code=404, detail="Incident not found")
    return result

@router.delete("/hard/{incident_id}", response_model=IncidentRead)
def hard_delete(incident_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = IncidentRepository(db, redis).hard_delete(incident_id)
    if not result:
        raise HTTPException(status_code=404, detail="Incident not found")
    return result

@router.get("/search/{keyword}", response_model=list[IncidentRead])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return IncidentRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    incidents = db.query(Incident).filter_by(is_deleted=False).all()
    for incident in incidents:
        index_incident(incident)
    return {"message": f"{len(incidents)} incidents indexed to Elasticsearch"}
