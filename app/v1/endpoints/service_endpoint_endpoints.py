from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.service_endpoint import (
    ServiceEndpointCreate,
    ServiceEndpointUpdate,
    ServiceEndpointInDB
)
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.service_endpoint_repository import ServiceEndpointRepository
from app.db.models.service_endpoint import ServiceEndpoint
from app.services.elasticsearch.service_endpoint_service import index_service_endpoint

router = APIRouter()

@router.get("/", response_model=list[ServiceEndpointInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return ServiceEndpointRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[ServiceEndpointInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return ServiceEndpointRepository(db, redis).get_all_soft_deleted()

@router.get("/{endpoint_id}", response_model=ServiceEndpointInDB)
def get_by_id(endpoint_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoint = ServiceEndpointRepository(db, redis).get_by_id(endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Service endpoint not found")
    return endpoint

@router.post("/", response_model=ServiceEndpointInDB)
def create(data: ServiceEndpointCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoint = ServiceEndpointRepository(db, redis).create(data.dict())
    index_service_endpoint(endpoint)
    return endpoint

@router.put("/{endpoint_id}", response_model=ServiceEndpointInDB)
def update(endpoint_id: UUID, data: ServiceEndpointUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoint = ServiceEndpointRepository(db, redis).update(endpoint_id, data.dict(exclude_unset=True))
    if not endpoint:
        raise HTTPException(status_code=404, detail="Service endpoint not found")
    db.refresh(endpoint)
    index_service_endpoint(endpoint)
    return endpoint

@router.delete("/soft/{endpoint_id}", response_model=ServiceEndpointInDB)
def soft_delete(endpoint_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoint = ServiceEndpointRepository(db, redis).soft_delete(endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Service endpoint not found")
    return endpoint

@router.put("/restore/{endpoint_id}", response_model=ServiceEndpointInDB)
def restore(endpoint_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoint = ServiceEndpointRepository(db, redis).restore(endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Service endpoint not found")
    return endpoint

@router.delete("/hard/{endpoint_id}", response_model=ServiceEndpointInDB)
def hard_delete(endpoint_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoint = ServiceEndpointRepository(db, redis).hard_delete(endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Service endpoint not found")
    return endpoint

@router.get("/search/{keyword}", response_model=list[ServiceEndpointInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return ServiceEndpointRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    endpoints = db.query(ServiceEndpoint).filter_by(is_deleted=False).all()
    for endpoint in endpoints:
        index_service_endpoint(endpoint)
    return {"message": f"{len(endpoints)} service endpoints indexed to Elasticsearch"}
