from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.service import Service


class ServiceRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[Service]:
        return self.db.query(Service).filter_by(is_deleted=False).all()

    def get_by_id(self, service_id: str) -> Optional[Service]:
        return self.db.query(Service).filter_by(service_id=service_id, is_deleted=False).first()

    def create(self, service_data: dict) -> Service:
        service = Service(**service_data)
        self.db.add(service)
        self.db.commit()
        self.db.refresh(service)
        return service

    def update(self, service_id: str, update_data: dict) -> Optional[Service]:
        service = self.db.query(Service).filter_by(service_id=service_id, is_deleted=False).first()
        if not service:
            return None
        for key, value in update_data.items():
            setattr(service, key, value)
        self.db.commit()
        self.db.refresh(service)
        return service

    def soft_delete(self, service_id: str) -> Optional[Service]:
        service = self.db.query(Service).filter_by(service_id=service_id, is_deleted=False).first()
        if not service:
            return None
        service.is_deleted = True
        service.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"service:{service_id}")
        self.redis.delete("services:all")
        return service

    def restore(self, service_id: str) -> Optional[Service]:
        service = self.db.query(Service).filter_by(service_id=service_id, is_deleted=True).first()
        if not service:
            return None
        service.is_deleted = False
        service.deleted_at = None
        self.db.commit()
        self.redis.delete(f"service:{service_id}")
        self.redis.delete("services:all")
        return service

    def hard_delete(self, service_id: str) -> Optional[Service]:
        service = self.db.query(Service).filter_by(service_id=service_id).first()
        if not service:
            return None
        self.db.delete(service)
        self.db.commit()
        self.redis.delete(f"service:{service_id}")
        self.redis.delete("services:all")
        return service

    def get_all_soft_deleted(self) -> List[Service]:
        return self.db.query(Service).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[Service]:
        try:
            result = es.search(
                index="services",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["name", "description", "criticality_level"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["service_id"] for hit in hits]
            return self.db.query(Service).filter(Service.service_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
