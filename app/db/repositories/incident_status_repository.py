from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models.incident_status import IncidentStatus
from typing import List, Optional

class IncidentStatusRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[IncidentStatus]:
        return self.db.query(IncidentStatus).filter_by(is_deleted=False).all()

    def get_by_id(self, status_id: str) -> Optional[IncidentStatus]:
        return self.db.query(IncidentStatus).filter_by(status_id=status_id, is_deleted=False).first()

    def create(self, data: dict) -> IncidentStatus:
        status = IncidentStatus(**data)
        self.db.add(status)
        self.db.commit()
        self.db.refresh(status)
        return status

    def update(self, status_id: str, update_data: dict) -> Optional[IncidentStatus]:
        status = self.db.query(IncidentStatus).filter_by(status_id=status_id, is_deleted=False).first()
        if not status:
            return None
        for key, value in update_data.items():
            setattr(status, key, value)
        self.db.commit()
        self.db.refresh(status)
        return status

    def soft_delete(self, status_id: str) -> Optional[IncidentStatus]:
        status = self.db.query(IncidentStatus).filter_by(status_id=status_id, is_deleted=False).first()
        if not status:
            return None
        status.is_deleted = True
        status.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"incident_status:{status_id}")
        self.redis.delete("incident_statuses:all")
        return status

    def restore(self, status_id: str) -> Optional[IncidentStatus]:
        status = self.db.query(IncidentStatus).filter_by(status_id=status_id, is_deleted=True).first()
        if not status:
            return None
        status.is_deleted = False
        status.deleted_at = None
        self.db.commit()
        self.redis.delete(f"incident_status:{status_id}")
        self.redis.delete("incident_statuses:all")
        return status

    def hard_delete(self, status_id: str) -> Optional[IncidentStatus]:
        status = self.db.query(IncidentStatus).filter_by(status_id=status_id).first()
        if not status:
            return None
        self.db.delete(status)
        self.db.commit()
        self.redis.delete(f"incident_status:{status_id}")
        self.redis.delete("incident_statuses:all")
        return status

    def get_all_soft_deleted(self) -> List[IncidentStatus]:
        return self.db.query(IncidentStatus).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[IncidentStatus]:
        try:
            result = es.search(
                index="incident_statuses",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["name", "description"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["status_id"] for hit in hits]
            return self.db.query(IncidentStatus).filter(IncidentStatus.status_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch incident_status search failed: {e}")
            raise
