from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models.telemetry_source import TelemetrySource
from typing import List, Optional

class TelemetrySourceRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[TelemetrySource]:
        return self.db.query(TelemetrySource).filter_by(is_deleted=False).all()

    def get_by_id(self, source_id: str) -> Optional[TelemetrySource]:
        return self.db.query(TelemetrySource).filter_by(source_id=source_id, is_deleted=False).first()

    def create(self, source_data: dict) -> TelemetrySource:
        source = TelemetrySource(**source_data)
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    def update(self, source_id: str, update_data: dict) -> Optional[TelemetrySource]:
        source = self.db.query(TelemetrySource).filter_by(source_id=source_id, is_deleted=False).first()
        if not source:
            return None
        for key, value in update_data.items():
            setattr(source, key, value)
        self.db.commit()
        self.db.refresh(source)
        return source

    def soft_delete(self, source_id: str) -> Optional[TelemetrySource]:
        source = self.db.query(TelemetrySource).filter_by(source_id=source_id, is_deleted=False).first()
        if not source:
            return None
        source.is_deleted = True
        source.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"telemetry_source:{source_id}")
        self.redis.delete("telemetry_sources:all")
        return source

    def restore(self, source_id: str) -> Optional[TelemetrySource]:
        source = self.db.query(TelemetrySource).filter_by(source_id=source_id, is_deleted=True).first()
        if not source:
            return None
        source.is_deleted = False
        source.deleted_at = None
        self.db.commit()
        self.redis.delete(f"telemetry_source:{source_id}")
        self.redis.delete("telemetry_sources:all")
        return source

    def hard_delete(self, source_id: str) -> Optional[TelemetrySource]:
        source = self.db.query(TelemetrySource).filter_by(source_id=source_id).first()
        if not source:
            return None
        self.db.delete(source)
        self.db.commit()
        self.redis.delete(f"telemetry_source:{source_id}")
        self.redis.delete("telemetry_sources:all")
        return source

    def get_all_soft_deleted(self) -> List[TelemetrySource]:
        return self.db.query(TelemetrySource).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[TelemetrySource]:
        try:
            result = es.search(
                index="telemetry_sources",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["name"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["source_id"] for hit in hits]
            return self.db.query(TelemetrySource).filter(TelemetrySource.source_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
