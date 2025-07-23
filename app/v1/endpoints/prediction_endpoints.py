from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.prediction import PredictionCreate, PredictionUpdate, PredictionInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.prediction_repository import PredictionRepository
from app.db.models.prediction import Prediction
from app.services.elasticsearch.prediction_service import index_prediction
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    predictions = PredictionRepository(db, redis).get_all()
    return success_response(serialize(predictions, PredictionInDB), "Predictions fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    predictions = PredictionRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(predictions, PredictionInDB), "Deleted predictions fetched successfully.")


@router.get("/{prediction_id}")
def get_by_id(prediction_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    prediction = PredictionRepository(db, redis).get_by_id(prediction_id)
    if not prediction:
        return error_response("Prediction not found", 404)
    return success_response(serialize(prediction, PredictionInDB), "Prediction fetched successfully.")


@router.post("/")
def create(data: PredictionCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    prediction = PredictionRepository(db, redis).create(data.dict())
    index_prediction(prediction)
    return success_response(serialize(prediction, PredictionInDB), "Prediction created successfully.", 201)


@router.put("/{prediction_id}")
def update(prediction_id: UUID, data: PredictionUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = PredictionRepository(db, redis).update(prediction_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Prediction not found", 404)
    index_prediction(result)
    return success_response(serialize(result, PredictionInDB), "Prediction updated successfully.")


@router.delete("/soft/{prediction_id}")
def soft_delete(prediction_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = PredictionRepository(db, redis).soft_delete(prediction_id)
    if not result:
        return error_response("Prediction not found", 404)
    return success_response(serialize(result, PredictionInDB), "Prediction soft deleted successfully.")


@router.put("/restore/{prediction_id}")
def restore(prediction_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = PredictionRepository(db, redis).restore(prediction_id)
    if not result:
        return error_response("Prediction not found", 404)
    return success_response(serialize(result, PredictionInDB), "Prediction restored successfully.")


@router.delete("/hard/{prediction_id}")
def hard_delete(prediction_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = PredictionRepository(db, redis).hard_delete(prediction_id)
    if not result:
        return error_response("Prediction not found", 404)
    return success_response(serialize(result, PredictionInDB), "Prediction permanently deleted.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = PredictionRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, PredictionInDB), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    predictions = db.query(Prediction).filter_by(is_deleted=False).all()
    for prediction in predictions:
        index_prediction(prediction)
    return success_response({"count": len(predictions)}, "All predictions indexed to Elasticsearch.")
