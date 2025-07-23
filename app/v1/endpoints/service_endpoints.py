from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.service import ServiceCreate, ServiceUpdate, ServiceInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.service_repository import ServiceRepository
from app.db.models.service import Service
from app.services.elasticsearch.service_service import index_service

router = APIRouter()

@router.get("/", response_model=list[ServiceInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return ServiceRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[ServiceInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return ServiceRepository(db, redis).get_all_soft_deleted()

@router.get("/{service_id}", response_model=ServiceInDB)
def get_by_id(service_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    service = ServiceRepository(db, redis).get_by_id(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service

@router.post("/", response_model=ServiceInDB)
def create(data: ServiceCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    service = ServiceRepository(db, redis).create(data.dict())
    index_service(service)
    return service

@router.put("/{service_id}", response_model=ServiceInDB)
def update(service_id: UUID, data: ServiceUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    service = ServiceRepository(db, redis).update(service_id, data.dict(exclude_unset=True))
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    db.refresh(service)
    index_service(service)
    return service

@router.delete("/soft/{service_id}", response_model=ServiceInDB)
def soft_delete(service_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    service = ServiceRepository(db, redis).soft_delete(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service

@router.put("/restore/{service_id}", response_model=ServiceInDB)
def restore(service_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    service = ServiceRepository(db, redis).restore(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service

@router.delete("/hard/{service_id}", response_model=ServiceInDB)
def hard_delete(service_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    service = ServiceRepository(db, redis).hard_delete(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service

@router.get("/search/{keyword}", response_model=list[ServiceInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return ServiceRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    services = db.query(Service).filter_by(is_deleted=False).all()
    for service in services:
        index_service(service)
    return {"message": f"{len(services)} services indexed to Elasticsearch"}
