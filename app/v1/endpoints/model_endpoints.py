from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.model import ModelCreate, ModelUpdate, ModelOut
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.model_repository import ModelRepository
from app.db.models.model import Model
from app.utils.response import success_response, error_response
from sqlalchemy import func, cast, Float
from app.services.elasticsearch.model_service import index_model

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/stats/summary")
def models_summary(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    acc_as_float = cast(func.nullif(Model.accuracy, ''), Float)

    avg_q = db.query(func.avg(acc_as_float)).filter(
        Model.is_deleted == False,        
        acc_as_float > 0                  
    )
    avg_accuracy = avg_q.scalar()
    avg_accuracy = float(avg_accuracy) if avg_accuracy is not None else 0.0

  
    active_q = db.query(func.count(Model.model_id)).filter(
        Model.is_deleted == False,           
        Model.last_training_status == "succeeded"
    )
    active_models = int(active_q.scalar() or 0)

    return success_response(
        {
            "avg_accuracy": round(avg_accuracy, 4),
            "active_models": active_models
        },
        "Model summary computed successfully."
    )

@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    models = ModelRepository(db, redis).get_all()
    return success_response(serialize(models, ModelOut), "Models fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    models = ModelRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(models, ModelOut), "Soft-deleted models fetched successfully.")


@router.get("/{model_id}")
def get_by_id(model_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    model = ModelRepository(db, redis).get_by_id(model_id)
    if not model:
        return error_response("Model not found", 404)
    return success_response(serialize(model, ModelOut), "Model fetched successfully.")


@router.post("/")
def create(data: ModelCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    model = ModelRepository(db, redis).create(data.dict())
    index_model(model)
    return success_response(serialize(model, ModelOut), "Model created successfully.", 201)


@router.put("/{model_id}")
def update(model_id: UUID, data: ModelUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ModelRepository(db, redis).update(model_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Model not found", 404)
    index_model(result)
    return success_response(serialize(result, ModelOut), "Model updated successfully.")


@router.delete("/soft/{model_id}")
def soft_delete(model_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ModelRepository(db, redis).soft_delete(model_id)
    if not result:
        return error_response("Model not found", 404)
    return success_response(serialize(result, ModelOut), "Model soft deleted successfully.")


@router.put("/restore/{model_id}")
def restore(model_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ModelRepository(db, redis).restore(model_id)
    if not result:
        return error_response("Model not found", 404)
    return success_response(serialize(result, ModelOut), "Model restored successfully.")


@router.delete("/hard/{model_id}")
def hard_delete(model_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ModelRepository(db, redis).hard_delete(model_id)
    if not result:
        return error_response("Model not found", 404)
    return success_response(serialize(result, ModelOut), "Model permanently deleted.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    try:
        results = ModelRepository(db, redis).search(keyword, es)
        return success_response(serialize(results, ModelOut), f"Search results for keyword '{keyword}'.")
    except Exception as e:
        return error_response(f"Elasticsearch error: {str(e)}", 503)


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    models = db.query(Model).filter_by(is_deleted=False).all()
    for model in models:
        index_model(model)
    return success_response({"count": len(models)}, "All models indexed to Elasticsearch.")
