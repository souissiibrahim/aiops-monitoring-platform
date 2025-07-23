from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models.environment import Environment
from typing import List, Optional


class EnvironmentRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[Environment]:
        return self.db.query(Environment).filter_by(is_deleted=False).all()

    def get_by_id(self, environment_id: str) -> Optional[Environment]:
        return self.db.query(Environment).filter_by(environment_id=environment_id, is_deleted=False).first()

    def create(self, data: dict) -> Environment:
        environment = Environment(**data)
        self.db.add(environment)
        self.db.commit()
        self.db.refresh(environment)
        return environment

    def update(self, environment_id: str, update_data: dict) -> Optional[Environment]:
        environment = self.db.query(Environment).filter_by(environment_id=environment_id, is_deleted=False).first()
        if not environment:
            return None
        for key, value in update_data.items():
            setattr(environment, key, value)
        self.db.commit()
        self.db.refresh(environment)
        return environment

    def soft_delete(self, environment_id: str) -> Optional[Environment]:
        environment = self.db.query(Environment).filter_by(environment_id=environment_id, is_deleted=False).first()
        if not environment:
            return None
        environment.is_deleted = True
        environment.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"environment:{environment_id}")
        self.redis.delete("environments:all")
        return environment

    def restore(self, environment_id: str) -> Optional[Environment]:
        environment = self.db.query(Environment).filter_by(environment_id=environment_id, is_deleted=True).first()
        if not environment:
            return None
        environment.is_deleted = False
        environment.deleted_at = None
        self.db.commit()
        self.redis.delete(f"environment:{environment_id}")
        self.redis.delete("environments:all")
        return environment

    def hard_delete(self, environment_id: str) -> Optional[Environment]:
        environment = self.db.query(Environment).filter_by(environment_id=environment_id).first()
        if not environment:
            return None
        self.db.delete(environment)
        self.db.commit()
        self.redis.delete(f"environment:{environment_id}")
        self.redis.delete("environments:all")
        return environment

    def get_all_soft_deleted(self) -> List[Environment]:
        return self.db.query(Environment).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[Environment]:
        try:
            result = es.search(
                index="environments",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["name", "description"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["environment_id"] for hit in hits]
            return self.db.query(Environment).filter(Environment.environment_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
