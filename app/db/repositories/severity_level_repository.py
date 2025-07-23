from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.severity_level import SeverityLevel
from elasticsearch import Elasticsearch


class SeverityLevelRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[SeverityLevel]:
        return self.db.query(SeverityLevel).filter_by(is_deleted=False).all()

    def get_by_id(self, severity_level_id: str) -> Optional[SeverityLevel]:
        return self.db.query(SeverityLevel).filter_by(severity_level_id=severity_level_id, is_deleted=False).first()

    def create(self, severity_level_data: dict) -> SeverityLevel:
        severity_level = SeverityLevel(**severity_level_data)
        self.db.add(severity_level)
        self.db.commit()
        self.db.refresh(severity_level)
        return severity_level

    def update(self, severity_level_id: str, update_data: dict) -> Optional[SeverityLevel]:
        severity_level = self.db.query(SeverityLevel).filter_by(severity_level_id=severity_level_id, is_deleted=False).first()
        if not severity_level:
            return None

        for key, value in update_data.items():
            setattr(severity_level, key, value)

        self.db.commit()
        self.db.refresh(severity_level)
        return severity_level

    def soft_delete(self, severity_level_id: str) -> Optional[SeverityLevel]:
        severity_level = self.db.query(SeverityLevel).filter_by(severity_level_id=severity_level_id, is_deleted=False).first()
        if not severity_level:
            return None

        severity_level.is_deleted = True
        severity_level.deleted_at = func.now()
        self.db.commit()

        self.redis.delete(f"severity_level:{severity_level_id}")
        self.redis.delete("severity_levels:all")
        return severity_level

    def restore(self, severity_level_id: str) -> Optional[SeverityLevel]:
        severity_level = self.db.query(SeverityLevel).filter_by(severity_level_id=severity_level_id, is_deleted=True).first()
        if not severity_level:
            return None

        severity_level.is_deleted = False
        severity_level.deleted_at = None
        self.db.commit()

        self.redis.delete(f"severity_level:{severity_level_id}")
        self.redis.delete("severity_levels:all")
        return severity_level

    def hard_delete(self, severity_level_id: str) -> Optional[SeverityLevel]:
        severity_level = self.db.query(SeverityLevel).filter_by(severity_level_id=severity_level_id).first()
        if not severity_level:
            return None

        self.db.delete(severity_level)
        self.db.commit()

        self.redis.delete(f"severity_level:{severity_level_id}")
        self.redis.delete("severity_levels:all")
        return severity_level

    def get_all_soft_deleted(self) -> List[SeverityLevel]:
        return self.db.query(SeverityLevel).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es: Elasticsearch) -> List[SeverityLevel]:
        try:
            result = es.search(
                index="severity_levels",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["name", "description"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["severity_level_id"] for hit in hits]
            return self.db.query(SeverityLevel).filter(SeverityLevel.severity_level_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
