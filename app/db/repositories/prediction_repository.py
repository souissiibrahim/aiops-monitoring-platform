from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.prediction import Prediction

class PredictionRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[Prediction]:
        return self.db.query(Prediction).filter_by(is_deleted=False).all()

    def get_by_id(self, prediction_id: str) -> Optional[Prediction]:
        return self.db.query(Prediction).filter_by(prediction_id=prediction_id, is_deleted=False).first()

    def create(self, data: dict) -> Prediction:
        prediction = Prediction(**data)
        self.db.add(prediction)
        self.db.commit()
        self.db.refresh(prediction)
        return prediction

    def update(self, prediction_id: str, update_data: dict) -> Optional[Prediction]:
        prediction = self.db.query(Prediction).filter_by(prediction_id=prediction_id, is_deleted=False).first()
        if not prediction:
            return None

        for key, value in update_data.items():
            setattr(prediction, key, value)

        self.db.commit()
        self.db.refresh(prediction)
        return prediction

    def soft_delete(self, prediction_id: str) -> Optional[Prediction]:
        prediction = self.db.query(Prediction).filter_by(prediction_id=prediction_id, is_deleted=False).first()
        if not prediction:
            return None

        prediction.is_deleted = True
        prediction.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"prediction:{prediction_id}")
        self.redis.delete("predictions:all")
        return prediction

    def restore(self, prediction_id: str) -> Optional[Prediction]:
        prediction = self.db.query(Prediction).filter_by(prediction_id=prediction_id, is_deleted=True).first()
        if not prediction:
            return None

        prediction.is_deleted = False
        prediction.deleted_at = None
        self.db.commit()
        self.redis.delete(f"prediction:{prediction_id}")
        self.redis.delete("predictions:all")
        return prediction

    def hard_delete(self, prediction_id: str) -> Optional[Prediction]:
        prediction = self.db.query(Prediction).filter_by(prediction_id=prediction_id).first()
        if not prediction:
            return None

        self.db.delete(prediction)
        self.db.commit()
        self.redis.delete(f"prediction:{prediction_id}")
        self.redis.delete("predictions:all")
        return prediction

    def get_all_soft_deleted(self) -> List[Prediction]:
        return self.db.query(Prediction).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[Prediction]:
        try:
            result = es.search(
                index="predictions",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["status"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["prediction_id"] for hit in hits]
            return self.db.query(Prediction).filter(Prediction.prediction_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch Prediction search failed: {e}")
            raise
