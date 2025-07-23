from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models.dependency_graph import DependencyGraph
from typing import List, Optional
from uuid import UUID


class DependencyGraphRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[DependencyGraph]:
        return self.db.query(DependencyGraph).filter_by(is_deleted=False).all()

    def get_by_id(self, dependency_id: UUID) -> Optional[DependencyGraph]:
        return self.db.query(DependencyGraph).filter_by(dependency_id=dependency_id, is_deleted=False).first()

    def create(self, data: dict) -> DependencyGraph:
        dependency = DependencyGraph(**data)
        self.db.add(dependency)
        self.db.commit()
        self.db.refresh(dependency)
        return dependency

    def update(self, dependency_id: UUID, update_data: dict) -> Optional[DependencyGraph]:
        dependency = self.db.query(DependencyGraph).filter_by(dependency_id=dependency_id, is_deleted=False).first()
        if not dependency:
            return None
        for key, value in update_data.items():
            setattr(dependency, key, value)
        self.db.commit()
        self.db.refresh(dependency)
        return dependency

    def soft_delete(self, dependency_id: UUID) -> Optional[DependencyGraph]:
        dependency = self.db.query(DependencyGraph).filter_by(dependency_id=dependency_id, is_deleted=False).first()
        if not dependency:
            return None
        dependency.is_deleted = True
        dependency.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"dependency_graph:{dependency_id}")
        self.redis.delete("dependency_graph:all")
        return dependency

    def restore(self, dependency_id: UUID) -> Optional[DependencyGraph]:
        dependency = self.db.query(DependencyGraph).filter_by(dependency_id=dependency_id, is_deleted=True).first()
        if not dependency:
            return None
        dependency.is_deleted = False
        dependency.deleted_at = None
        self.db.commit()
        self.redis.delete(f"dependency_graph:{dependency_id}")
        self.redis.delete("dependency_graph:all")
        return dependency

    def hard_delete(self, dependency_id: UUID) -> Optional[DependencyGraph]:
        dependency = self.db.query(DependencyGraph).filter_by(dependency_id=dependency_id).first()
        if not dependency:
            return None
        self.db.delete(dependency)
        self.db.commit()
        self.redis.delete(f"dependency_graph:{dependency_id}")
        self.redis.delete("dependency_graph:all")
        return dependency

    def get_all_soft_deleted(self) -> List[DependencyGraph]:
        return self.db.query(DependencyGraph).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[dict]:
        query = {
            "query": {
                "multi_match": {
                    "query": keyword,
                    "fields": ["dependency_type"]
                }
            }
        }
        result = es.search(index="dependency_graph", body=query)
        return [hit["_source"] for hit in result["hits"]["hits"]]
