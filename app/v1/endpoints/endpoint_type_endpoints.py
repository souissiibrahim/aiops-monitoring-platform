from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.endpoint_type import (
    EndpointTypeCreate,
    EndpointTypeUpdate,
    EndpointTypeInDB,
)
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.endpoint_type_repository import EndpointTypeRepository
from app.db.models.endpoint_type import EndpointType
from app.services.elasticsearch.endpoint_type_service import index_endpoint_type

router = APIRouter()

@router.get("/", response_model=list[EndpointTypeInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return EndpointTypeRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[EndpointTypeInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return EndpointTypeRepository(db, redis).get_all_soft_deleted()

@router.get("/{endpoint_type_id}", response_model=EndpointTypeInDB)
def get_by_id(endpoint_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EndpointTypeRepository(db, redis).get_by_id(endpoint_type_id)
    if not result:
        raise HTTPException(status_code=404, detail="Endpoint type not found")
    return result

@router.post("/", response_model=EndpointTypeInDB)
def create(data: EndpointTypeCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoint_type = EndpointTypeRepository(db, redis).create(data.dict())
    try:
        index_endpoint_type(endpoint_type)
    except Exception as e:
        print(f"❌ Failed to index endpoint type after creation: {e}")
    return endpoint_type

@router.put("/{endpoint_type_id}", response_model=EndpointTypeInDB)
def update(endpoint_type_id: UUID, data: EndpointTypeUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EndpointTypeRepository(db, redis).update(endpoint_type_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Endpoint type not found")
    try:
        index_endpoint_type(result)
    except Exception as e:
        print(f"❌ Failed to index endpoint type after update: {e}")
    return result

@router.delete("/soft/{endpoint_type_id}", response_model=EndpointTypeInDB)
def soft_delete(endpoint_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EndpointTypeRepository(db, redis).soft_delete(endpoint_type_id)
    if not result:
        raise HTTPException(status_code=404, detail="Endpoint type not found")
    return result

@router.put("/restore/{endpoint_type_id}", response_model=EndpointTypeInDB)
def restore(endpoint_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EndpointTypeRepository(db, redis).restore(endpoint_type_id)
    if not result:
        raise HTTPException(status_code=404, detail="Endpoint type not found")
    return result

@router.delete("/hard/{endpoint_type_id}", response_model=EndpointTypeInDB)
def hard_delete(endpoint_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EndpointTypeRepository(db, redis).hard_delete(endpoint_type_id)
    if not result:
        raise HTTPException(status_code=404, detail="Endpoint type not found")
    return result

@router.get("/search/{keyword}", response_model=list[EndpointTypeInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return EndpointTypeRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    endpoint_types = db.query(EndpointType).filter_by(is_deleted=False).all()
    for et in endpoint_types:
        index_endpoint_type(et)
    return {"message": f"{len(endpoint_types)} endpoint types indexed to Elasticsearch"}
