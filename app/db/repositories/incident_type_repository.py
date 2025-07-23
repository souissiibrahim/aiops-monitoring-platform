from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.incident_type import IncidentType

class IncidentTypeRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[IncidentType]:
        return self.db.query(IncidentType).filter_by(is_deleted=False).all()

    def get_by_id(self, incident_type_id: str) -> Optional[IncidentType]:
        return self.db.query(IncidentType).filter_by(incident_type_id=incident_type_id, is_deleted=False).first()

    def create(self, data: dict) -> IncidentType:
        obj = IncidentType(**data)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, incident_type_id: str, update_data: dict) -> Optional[IncidentType]:
        obj = self.db.query(IncidentType).filter_by(incident_type_id=incident_type_id, is_deleted=False).first()
        if not obj:
            return None
        for key, value in update_data.items():
            setattr(obj, key, value)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def soft_delete(self, incident_type_id: str) -> Optional[IncidentType]:
        obj = self.db.query(IncidentType).filter_by(incident_type_id=incident_type_id, is_deleted=False).first()
        if not obj:
            return None
        obj.is_deleted = True
        obj.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"incident_type:{incident_type_id}")
        self.redis.delete("incident_types:all")
        return obj

    def restore(self, incident_type_id: str) -> Optional[IncidentType]:
        obj = self.db.query(IncidentType).filter_by(incident_type_id=incident_type_id, is_deleted=True).first()
        if not obj:
            return None
        obj.is_deleted = False
        obj.deleted_at = None
        self.db.commit()
        self.redis.delete(f"incident_type:{incident_type_id}")
        self.redis.delete("incident_types:all")
        return obj

    def hard_delete(self, incident_type_id: str) -> Optional[IncidentType]:
        obj = self.db.query(IncidentType).filter_by(incident_type_id=incident_type_id).first()
        if not obj:
            return None
        self.db.delete(obj)
        self.db.commit()
        self.redis.delete(f"incident_type:{incident_type_id}")
        self.redis.delete("incident_types:all")
        return obj

    def get_all_soft_deleted(self) -> List[IncidentType]:
        return self.db.query(IncidentType).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[IncidentType]:
        try:
            result = es.search(
                index="incident_types",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["name", "description", "category"],
                        "type": "best_fields"
                    }
                }
            )
            ids = [hit["_source"]["incident_type_id"] for hit in result["hits"]["hits"]]
            return self.db.query(IncidentType).filter(IncidentType.incident_type_id.in_(ids)).all()
        except Exception as e:
            print(f"\u274c Elasticsearch search failed: {e}")
            raise