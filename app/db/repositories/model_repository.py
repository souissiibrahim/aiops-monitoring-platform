from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.model import Model

class ModelRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[Model]:
        return self.db.query(Model).filter_by(is_deleted=False).all()

    def get_by_id(self, model_id: str) -> Optional[Model]:
        return self.db.query(Model).filter_by(model_id=model_id, is_deleted=False).first()

    def create(self, data: dict) -> Model:
        model = Model(**data)
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def update(self, model_id: str, update_data: dict) -> Optional[Model]:
        model = self.db.query(Model).filter_by(model_id=model_id, is_deleted=False).first()
        if not model:
            return None
        for key, value in update_data.items():
            setattr(model, key, value)
        self.db.commit()
        self.db.refresh(model)
        return model

    def soft_delete(self, model_id: str) -> Optional[Model]:
        model = self.db.query(Model).filter_by(model_id=model_id, is_deleted=False).first()
        if not model:
            return None
        model.is_deleted = True
        model.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"model:{model_id}")
        self.redis.delete("models:all")
        return model

    def restore(self, model_id: str) -> Optional[Model]:
        model = self.db.query(Model).filter_by(model_id=model_id, is_deleted=True).first()
        if not model:
            return None
        model.is_deleted = False
        model.deleted_at = None
        self.db.commit()
        self.redis.delete(f"model:{model_id}")
        self.redis.delete("models:all")
        return model

    def hard_delete(self, model_id: str) -> Optional[Model]:
        model = self.db.query(Model).filter_by(model_id=model_id).first()
        if not model:
            return None
        self.db.delete(model)
        self.db.commit()
        self.redis.delete(f"model:{model_id}")
        self.redis.delete("models:all")
        return model

    def get_all_soft_deleted(self) -> List[Model]:
        return self.db.query(Model).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[Model]:
        try:
            result = es.search(
                index="models",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["name", "type", "version"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["model_id"] for hit in hits]
            return self.db.query(Model).filter(Model.model_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch model search failed: {e}")
            raise


