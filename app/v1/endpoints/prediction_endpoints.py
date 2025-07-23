from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.prediction import PredictionCreate, PredictionUpdate, PredictionInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.prediction_repository import PredictionRepository
from app.db.models.prediction import Prediction
from app.services.elasticsearch.prediction_service import index_prediction


router = APIRouter()

@router.get("/", response_model=list[PredictionInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return PredictionRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[PredictionInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return PredictionRepository(db, redis).get_all_soft_deleted()

@router.get("/{prediction_id}", response_model=PredictionInDB)
def get_by_id(prediction_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    prediction = PredictionRepository(db, redis).get_by_id(prediction_id)
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return prediction

@router.post("/", response_model=PredictionInDB)
def create(data: PredictionCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return PredictionRepository(db, redis).create(data.dict())

@router.put("/{prediction_id}", response_model=PredictionInDB)
def update(prediction_id: UUID, data: PredictionUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = PredictionRepository(db, redis).update(prediction_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return result

@router.delete("/soft/{prediction_id}", response_model=PredictionInDB)
def soft_delete(prediction_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = PredictionRepository(db, redis).soft_delete(prediction_id)
    if not result:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return result

@router.put("/restore/{prediction_id}", response_model=PredictionInDB)
def restore(prediction_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = PredictionRepository(db, redis).restore(prediction_id)
    if not result:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return result

@router.delete("/hard/{prediction_id}", response_model=PredictionInDB)
def hard_delete(prediction_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = PredictionRepository(db, redis).hard_delete(prediction_id)
    if not result:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return result

@router.get("/search/{keyword}", response_model=list[PredictionInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return PredictionRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    predictions = db.query(Prediction).filter_by(is_deleted=False).all()
    for prediction in predictions:
        index_prediction(prediction)
    return {"message": f"{len(predictions)} predictions indexed to Elasticsearch"}