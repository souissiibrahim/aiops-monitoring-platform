from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models.shap_explanation import ShapExplanation
from typing import List, Optional


class ShapExplanationRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[ShapExplanation]:
        return self.db.query(ShapExplanation).filter_by(is_deleted=False).all()

    def get_by_id(self, explanation_id: str) -> Optional[ShapExplanation]:
        return self.db.query(ShapExplanation).filter_by(explanation_id=explanation_id, is_deleted=False).first()

    def create(self, explanation_data: dict) -> ShapExplanation:
        explanation = ShapExplanation(**explanation_data)
        self.db.add(explanation)
        self.db.commit()
        self.db.refresh(explanation)
        return explanation

    def update(self, explanation_id: str, update_data: dict) -> Optional[ShapExplanation]:
        explanation = self.db.query(ShapExplanation).filter_by(explanation_id=explanation_id, is_deleted=False).first()
        if not explanation:
            return None

        for key, value in update_data.items():
            setattr(explanation, key, value)

        self.db.commit()
        self.db.refresh(explanation)
        return explanation

    def soft_delete(self, explanation_id: str) -> Optional[ShapExplanation]:
        explanation = self.db.query(ShapExplanation).filter_by(explanation_id=explanation_id, is_deleted=False).first()
        if not explanation:
            return None

        explanation.is_deleted = True
        explanation.deleted_at = func.now()
        self.db.commit()

        self.redis.delete(f"shap_explanation:{explanation_id}")
        self.redis.delete("shap_explanations:all")
        return explanation

    def restore(self, explanation_id: str) -> Optional[ShapExplanation]:
        explanation = self.db.query(ShapExplanation).filter_by(explanation_id=explanation_id, is_deleted=True).first()
        if not explanation:
            return None

        explanation.is_deleted = False
        explanation.deleted_at = None
        self.db.commit()

        self.redis.delete(f"shap_explanation:{explanation_id}")
        self.redis.delete("shap_explanations:all")
        return explanation

    def hard_delete(self, explanation_id: str) -> Optional[ShapExplanation]:
        explanation = self.db.query(ShapExplanation).filter_by(explanation_id=explanation_id).first()
        if not explanation:
            return None

        self.db.delete(explanation)
        self.db.commit()

        self.redis.delete(f"shap_explanation:{explanation_id}")
        self.redis.delete("shap_explanations:all")
        return explanation

    def get_all_soft_deleted(self) -> List[ShapExplanation]:
        return self.db.query(ShapExplanation).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[ShapExplanation]:
        try:
            result = es.search(
                index="shap_explanations",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["explanation_text"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["explanation_id"] for hit in hits]
            return self.db.query(ShapExplanation).filter(ShapExplanation.explanation_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
