from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.environment import EnvironmentCreate, EnvironmentUpdate, EnvironmentInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.models.environment import Environment
from app.db.repositories.environment_repository import EnvironmentRepository
from app.services.elasticsearch.environment_service import index_environment

router = APIRouter()

@router.get("/", response_model=list[EnvironmentInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return EnvironmentRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[EnvironmentInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return EnvironmentRepository(db, redis).get_all_soft_deleted()

@router.get("/{environment_id}", response_model=EnvironmentInDB)
def get_by_id(environment_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    env = EnvironmentRepository(db, redis).get_by_id(environment_id)
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    return env

@router.post("/", response_model=EnvironmentInDB)
def create(data: EnvironmentCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    env = EnvironmentRepository(db, redis).create(data.dict())
    index_environment(env)
    return env

@router.put("/{environment_id}", response_model=EnvironmentInDB)
def update(environment_id: UUID, data: EnvironmentUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EnvironmentRepository(db, redis).update(environment_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Environment not found")
    index_environment(result)
    return result

@router.delete("/soft/{environment_id}", response_model=EnvironmentInDB)
def soft_delete(environment_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EnvironmentRepository(db, redis).soft_delete(environment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Environment not found")
    return result

@router.put("/restore/{environment_id}", response_model=EnvironmentInDB)
def restore(environment_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EnvironmentRepository(db, redis).restore(environment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Environment not found")
    return result

@router.delete("/hard/{environment_id}", response_model=EnvironmentInDB)
def hard_delete(environment_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EnvironmentRepository(db, redis).hard_delete(environment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Environment not found")
    return result

@router.get("/search/{keyword}", response_model=list[EnvironmentInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return EnvironmentRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    environments = db.query(Environment).filter_by(is_deleted=False).all()
    for env in environments:
        index_environment(env)
    return {"message": f"{len(environments)} environments indexed to Elasticsearch"}
