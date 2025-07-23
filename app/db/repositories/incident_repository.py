from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models.incident import Incident
from typing import List, Optional


class IncidentRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[Incident]:
        return self.db.query(Incident).filter_by(is_deleted=False).all()

    def get_by_id(self, incident_id: str) -> Optional[Incident]:
        return self.db.query(Incident).filter_by(incident_id=incident_id, is_deleted=False).first()

    def create(self, incident_data: dict) -> Incident:
        incident = Incident(**incident_data)
        self.db.add(incident)
        self.db.commit()
        self.db.refresh(incident)
        return incident

    def update(self, incident_id: str, update_data: dict) -> Optional[Incident]:
        incident = self.db.query(Incident).filter_by(incident_id=incident_id, is_deleted=False).first()
        if not incident:
            return None

        for key, value in update_data.items():
            setattr(incident, key, value)

        self.db.commit()
        self.db.refresh(incident)
        return incident

    def soft_delete(self, incident_id: str) -> Optional[Incident]:
        incident = self.db.query(Incident).filter_by(incident_id=incident_id, is_deleted=False).first()
        if not incident:
            return None

        incident.is_deleted = True
        incident.deleted_at = func.now()
        self.db.commit()

        self.redis.delete(f"incident:{incident_id}")
        self.redis.delete("incidents:all")
        return incident

    def restore(self, incident_id: str) -> Optional[Incident]:
        incident = self.db.query(Incident).filter_by(incident_id=incident_id, is_deleted=True).first()
        if not incident:
            return None

        incident.is_deleted = False
        incident.deleted_at = None
        self.db.commit()

        self.redis.delete(f"incident:{incident_id}")
        self.redis.delete("incidents:all")
        return incident

    def hard_delete(self, incident_id: str) -> Optional[Incident]:
        incident = self.db.query(Incident).filter_by(incident_id=incident_id).first()
        if not incident:
            return None

        self.db.delete(incident)
        self.db.commit()

        self.redis.delete(f"incident:{incident_id}")
        self.redis.delete("incidents:all")
        return incident

    def get_all_soft_deleted(self) -> List[Incident]:
        return self.db.query(Incident).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[Incident]:
        try:
            result = es.search(
                index="incidents",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["description", "escalation_level"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["incident_id"] for hit in hits]
            return self.db.query(Incident).filter(Incident.incident_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
