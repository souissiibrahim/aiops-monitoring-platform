from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.shap_explanation import ShapExplanationCreate, ShapExplanationRead
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.shap_explanation_repository import ShapExplanationRepository
from app.db.models.shap_explanation import ShapExplanation
from app.services.elasticsearch.shap_explanation_service import index_shap_explanation
from app.utils.response import success_response, error_response

router = APIRouter()

def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    explanations = ShapExplanationRepository(db, redis).get_all()
    return success_response(serialize(explanations, ShapExplanationRead), "SHAP explanations fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    explanations = ShapExplanationRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(explanations, ShapExplanationRead), "Soft-deleted SHAP explanations fetched successfully.")


@router.get("/{explanation_id}")
def get_by_id(explanation_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    explanation = ShapExplanationRepository(db, redis).get_by_id(explanation_id)
    if not explanation:
        return error_response("SHAP explanation not found", 404)
    return success_response(serialize(explanation, ShapExplanationRead), "SHAP explanation fetched successfully.")


@router.post("/")
def create(data: ShapExplanationCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    explanation = ShapExplanationRepository(db, redis).create(data.dict())
    index_shap_explanation(explanation)
    return success_response(serialize(explanation, ShapExplanationRead), "SHAP explanation created successfully.", 201)


@router.put("/{explanation_id}")
def update(explanation_id: UUID, data: ShapExplanationCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    updated = ShapExplanationRepository(db, redis).update(explanation_id, data.dict(exclude_unset=True))
    if not updated:
        return error_response("SHAP explanation not found", 404)
    db.refresh(updated)
    index_shap_explanation(updated)
    return success_response(serialize(updated, ShapExplanationRead), "SHAP explanation updated successfully.")


@router.delete("/soft/{explanation_id}")
def soft_delete(explanation_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ShapExplanationRepository(db, redis).soft_delete(explanation_id)
    if not result:
        return error_response("SHAP explanation not found", 404)
    return success_response(serialize(result, ShapExplanationRead), "SHAP explanation soft deleted successfully.")


@router.put("/restore/{explanation_id}")
def restore(explanation_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ShapExplanationRepository(db, redis).restore(explanation_id)
    if not result:
        return error_response("SHAP explanation not found", 404)
    return success_response(serialize(result, ShapExplanationRead), "SHAP explanation restored successfully.")


@router.delete("/hard/{explanation_id}")
def hard_delete(explanation_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ShapExplanationRepository(db, redis).hard_delete(explanation_id)
    if not result:
        return error_response("SHAP explanation not found", 404)
    return success_response(serialize(result, ShapExplanationRead), "SHAP explanation permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = ShapExplanationRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, ShapExplanationRead), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    explanations = db.query(ShapExplanation).filter_by(is_deleted=False).all()
    for explanation in explanations:
        index_shap_explanation(explanation)
    return success_response({"count": len(explanations)}, "All SHAP explanations indexed to Elasticsearch.")
