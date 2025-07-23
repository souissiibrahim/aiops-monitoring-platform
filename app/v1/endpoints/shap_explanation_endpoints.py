from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.shap_explanation import ShapExplanationCreate, ShapExplanationRead
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.shap_explanation_repository import ShapExplanationRepository
from app.db.models.shap_explanation import ShapExplanation
from app.services.elasticsearch.shap_explanation_service import index_shap_explanation

router = APIRouter()

@router.get("/", response_model=list[ShapExplanationRead])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return ShapExplanationRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[ShapExplanationRead])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return ShapExplanationRepository(db, redis).get_all_soft_deleted()

@router.get("/{explanation_id}", response_model=ShapExplanationRead)
def get_by_id(explanation_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    explanation = ShapExplanationRepository(db, redis).get_by_id(explanation_id)
    if not explanation:
        raise HTTPException(status_code=404, detail="SHAP Explanation not found")
    return explanation

@router.post("/", response_model=ShapExplanationRead)
def create(data: ShapExplanationCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    explanation = ShapExplanationRepository(db, redis).create(data.dict())
    index_shap_explanation(explanation)
    return explanation

@router.put("/{explanation_id}", response_model=ShapExplanationRead)
def update(explanation_id: UUID, data: ShapExplanationCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    updated = ShapExplanationRepository(db, redis).update(explanation_id, data.dict(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="SHAP Explanation not found")
    db.refresh(updated)
    index_shap_explanation(updated)
    return updated

@router.delete("/soft/{explanation_id}", response_model=ShapExplanationRead)
def soft_delete(explanation_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ShapExplanationRepository(db, redis).soft_delete(explanation_id)
    if not result:
        raise HTTPException(status_code=404, detail="SHAP Explanation not found")
    return result

@router.put("/restore/{explanation_id}", response_model=ShapExplanationRead)
def restore(explanation_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ShapExplanationRepository(db, redis).restore(explanation_id)
    if not result:
        raise HTTPException(status_code=404, detail="SHAP Explanation not found")
    return result

@router.delete("/hard/{explanation_id}", response_model=ShapExplanationRead)
def hard_delete(explanation_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ShapExplanationRepository(db, redis).hard_delete(explanation_id)
    if not result:
        raise HTTPException(status_code=404, detail="SHAP Explanation not found")
    return result

@router.get("/search/{keyword}", response_model=list[ShapExplanationRead])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return ShapExplanationRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    explanations = db.query(ShapExplanation).filter_by(is_deleted=False).all()
    for explanation in explanations:
        index_shap_explanation(explanation)
    return {"message": f"{len(explanations)} SHAP explanations indexed to Elasticsearch"}
