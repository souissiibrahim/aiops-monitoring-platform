from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.model import ModelCreate, ModelUpdate, ModelOut
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.model_repository import ModelRepository
from app.db.models.model import Model

router = APIRouter()

@router.get("/", response_model=list[ModelOut])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return ModelRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[ModelOut])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return ModelRepository(db, redis).get_all_soft_deleted()

@router.get("/{model_id}", response_model=ModelOut)
def get_by_id(model_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    model = ModelRepository(db, redis).get_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model

@router.post("/", response_model=ModelOut)
def create(data: ModelCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return ModelRepository(db, redis).create(data.dict())

@router.put("/{model_id}", response_model=ModelOut)
def update(model_id: UUID, data: ModelUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ModelRepository(db, redis).update(model_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Model not found")
    return result

@router.delete("/soft/{model_id}", response_model=ModelOut)
def soft_delete(model_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ModelRepository(db, redis).soft_delete(model_id)
    if not result:
        raise HTTPException(status_code=404, detail="Model not found")
    return result

@router.put("/restore/{model_id}", response_model=ModelOut)
def restore(model_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ModelRepository(db, redis).restore(model_id)
    if not result:
        raise HTTPException(status_code=404, detail="Model not found")
    return result

@router.delete("/hard/{model_id}", response_model=ModelOut)
def hard_delete(model_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ModelRepository(db, redis).hard_delete(model_id)
    if not result:
        raise HTTPException(status_code=404, detail="Model not found")
    return result

@router.get("/search/{keyword}", response_model=list[ModelOut])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return ModelRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    from app.services.elasticsearch.model_service import index_model
    models = db.query(Model).filter_by(is_deleted=False).all()
    for model in models:
        index_model(model)
    return {"message": f"{len(models)} models indexed to Elasticsearch"}
