from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.service_endpoint import ServiceEndpoint


class ServiceEndpointRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[ServiceEndpoint]:
        return self.db.query(ServiceEndpoint).filter_by(is_deleted=False).all()

    def get_by_id(self, endpoint_id: str) -> Optional[ServiceEndpoint]:
        return self.db.query(ServiceEndpoint).filter_by(service_endpoint_id=endpoint_id, is_deleted=False).first()

    def create(self, endpoint_data: dict) -> ServiceEndpoint:
        endpoint = ServiceEndpoint(**endpoint_data)
        self.db.add(endpoint)
        self.db.commit()
        self.db.refresh(endpoint)
        return endpoint

    def update(self, endpoint_id: str, update_data: dict) -> Optional[ServiceEndpoint]:
        endpoint = self.db.query(ServiceEndpoint).filter_by(service_endpoint_id=endpoint_id, is_deleted=False).first()
        if not endpoint:
            return None
        for key, value in update_data.items():
            setattr(endpoint, key, value)
        self.db.commit()
        self.db.refresh(endpoint)
        return endpoint

    def soft_delete(self, endpoint_id: str) -> Optional[ServiceEndpoint]:
        endpoint = self.db.query(ServiceEndpoint).filter_by(service_endpoint_id=endpoint_id, is_deleted=False).first()
        if not endpoint:
            return None
        endpoint.is_deleted = True
        endpoint.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"service_endpoint:{endpoint_id}")
        self.redis.delete("service_endpoints:all")
        return endpoint

    def restore(self, endpoint_id: str) -> Optional[ServiceEndpoint]:
        endpoint = self.db.query(ServiceEndpoint).filter_by(service_endpoint_id=endpoint_id, is_deleted=True).first()
        if not endpoint:
            return None
        endpoint.is_deleted = False
        endpoint.deleted_at = None
        self.db.commit()
        self.redis.delete(f"service_endpoint:{endpoint_id}")
        self.redis.delete("service_endpoints:all")
        return endpoint

    def hard_delete(self, endpoint_id: str) -> Optional[ServiceEndpoint]:
        endpoint = self.db.query(ServiceEndpoint).filter_by(service_endpoint_id=endpoint_id).first()
        if not endpoint:
            return None
        self.db.delete(endpoint)
        self.db.commit()
        self.redis.delete(f"service_endpoint:{endpoint_id}")
        self.redis.delete("service_endpoints:all")
        return endpoint

    def get_all_soft_deleted(self) -> List[ServiceEndpoint]:
        return self.db.query(ServiceEndpoint).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[ServiceEndpoint]:
        try:
            result = es.search(
                index="service_endpoints",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["role_in_service"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["service_endpoint_id"] for hit in hits]
            return self.db.query(ServiceEndpoint).filter(ServiceEndpoint.service_endpoint_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
