from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.log_entry import LogEntry
from fastapi import HTTPException


class LogEntryRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[LogEntry]:
        return self.db.query(LogEntry).filter_by(is_deleted=False).all()

    def get_all_soft_deleted(self) -> List[LogEntry]:
        return self.db.query(LogEntry).filter_by(is_deleted=True).all()

    def get_by_id(self, log_id: int) -> Optional[LogEntry]:
        return self.db.query(LogEntry).filter_by(id=log_id, is_deleted=False).first()

    def create(self, log_data: dict) -> LogEntry:
        log_entry = LogEntry(**log_data)
        self.db.add(log_entry)
        self.db.commit()
        self.db.refresh(log_entry)
        return log_entry

    def update(self, log_id: int, update_data: dict) -> Optional[LogEntry]:
        log_entry = self.db.query(LogEntry).filter_by(id=log_id, is_deleted=False).first()
        if not log_entry:
            return None

        for key, value in update_data.items():
            setattr(log_entry, key, value)

        self.db.commit()
        self.db.refresh(log_entry)
        return log_entry

    def soft_delete(self, log_id: int) -> Optional[LogEntry]:
        log_entry = self.db.query(LogEntry).filter_by(id=log_id, is_deleted=False).first()
        if not log_entry:
            return None

        log_entry.is_deleted = True
        log_entry.deleted_at = func.now()
        self.db.commit()

        self.redis.delete(f"log:{log_id}")
        self.redis.delete("logs:all")
        return log_entry

    def restore(self, log_id: int) -> Optional[LogEntry]:
        log_entry = self.db.query(LogEntry).filter_by(id=log_id, is_deleted=True).first()
        if not log_entry:
            return None

        log_entry.is_deleted = False
        log_entry.deleted_at = None
        self.db.commit()

        self.redis.delete(f"log:{log_id}")
        self.redis.delete("logs:all")
        return log_entry

    def hard_delete(self, log_id: int) -> Optional[LogEntry]:
        log_entry = self.db.query(LogEntry).filter_by(id=log_id).first()
        if not log_entry:
            return None

        self.db.delete(log_entry)
        self.db.commit()

        self.redis.delete(f"log:{log_id}")
        self.redis.delete("logs:all")
        return log_entry

    def search(self, keyword: str, es) -> List[LogEntry]:
        try:
            result = es.search(
                index="log_entries",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["message", "level", "service"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [int(hit["_source"]["id"]) for hit in hits]
            return self.db.query(LogEntry).filter(LogEntry.id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise HTTPException(status_code=500, detail="Elasticsearch search error")
