from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models.audit_log import AuditLog
from typing import List, Optional


class AuditLogRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[AuditLog]:
        return self.db.query(AuditLog).filter_by(is_deleted=False).all()

    def get_by_id(self, log_id: str) -> Optional[AuditLog]:
        return self.db.query(AuditLog).filter_by(log_id=log_id, is_deleted=False).first()

    def create(self, data: dict) -> AuditLog:
        audit_log = AuditLog(**data)
        self.db.add(audit_log)
        self.db.commit()
        self.db.refresh(audit_log)
        return audit_log

    def update(self, log_id: str, update_data: dict) -> Optional[AuditLog]:
        audit_log = self.db.query(AuditLog).filter_by(log_id=log_id, is_deleted=False).first()
        if not audit_log:
            return None
        for key, value in update_data.items():
            setattr(audit_log, key, value)
        self.db.commit()
        self.db.refresh(audit_log)
        return audit_log

    def soft_delete(self, log_id: str) -> Optional[AuditLog]:
        audit_log = self.db.query(AuditLog).filter_by(log_id=log_id, is_deleted=False).first()
        if not audit_log:
            return None
        audit_log.is_deleted = True
        audit_log.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"audit_log:{log_id}")
        self.redis.delete("audit_logs:all")
        return audit_log

    def restore(self, log_id: str) -> Optional[AuditLog]:
        audit_log = self.db.query(AuditLog).filter_by(log_id=log_id, is_deleted=True).first()
        if not audit_log:
            return None
        audit_log.is_deleted = False
        audit_log.deleted_at = None
        self.db.commit()
        self.redis.delete(f"audit_log:{log_id}")
        self.redis.delete("audit_logs:all")
        return audit_log

    def hard_delete(self, log_id: str) -> Optional[AuditLog]:
        audit_log = self.db.query(AuditLog).filter_by(log_id=log_id).first()
        if not audit_log:
            return None
        self.db.delete(audit_log)
        self.db.commit()
        self.redis.delete(f"audit_log:{log_id}")
        self.redis.delete("audit_logs:all")
        return audit_log

    def get_all_soft_deleted(self) -> List[AuditLog]:
        return self.db.query(AuditLog).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[AuditLog]:
        try:
            result = es.search(
                index="audit_logs",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["action", "entity_type"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["log_id"] for hit in hits]
            return self.db.query(AuditLog).filter(AuditLog.log_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
