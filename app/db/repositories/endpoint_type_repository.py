from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.endpoint_type import EndpointType


class EndpointTypeRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[EndpointType]:
        return self.db.query(EndpointType).filter_by(is_deleted=False).all()

    def get_by_id(self, endpoint_type_id: str) -> Optional[EndpointType]:
        return self.db.query(EndpointType).filter_by(endpoint_type_id=endpoint_type_id, is_deleted=False).first()

    def create(self, data: dict) -> EndpointType:
        endpoint_type = EndpointType(**data)
        self.db.add(endpoint_type)
        self.db.commit()
        self.db.refresh(endpoint_type)
        return endpoint_type

    def update(self, endpoint_type_id: str, update_data: dict) -> Optional[EndpointType]:
        endpoint_type = self.db.query(EndpointType).filter_by(endpoint_type_id=endpoint_type_id, is_deleted=False).first()
        if not endpoint_type:
            return None
        for key, value in update_data.items():
            setattr(endpoint_type, key, value)
        self.db.commit()
        self.db.refresh(endpoint_type)
        return endpoint_type

    def soft_delete(self, endpoint_type_id: str) -> Optional[EndpointType]:
        endpoint_type = self.db.query(EndpointType).filter_by(endpoint_type_id=endpoint_type_id, is_deleted=False).first()
        if not endpoint_type:
            return None
        endpoint_type.is_deleted = True
        endpoint_type.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"endpoint_type:{endpoint_type_id}")
        self.redis.delete("endpoint_types:all")
        return endpoint_type

    def restore(self, endpoint_type_id: str) -> Optional[EndpointType]:
        endpoint_type = self.db.query(EndpointType).filter_by(endpoint_type_id=endpoint_type_id, is_deleted=True).first()
        if not endpoint_type:
            return None
        endpoint_type.is_deleted = False
        endpoint_type.deleted_at = None
        self.db.commit()
        self.redis.delete(f"endpoint_type:{endpoint_type_id}")
        self.redis.delete("endpoint_types:all")
        return endpoint_type

    def hard_delete(self, endpoint_type_id: str) -> Optional[EndpointType]:
        endpoint_type = self.db.query(EndpointType).filter_by(endpoint_type_id=endpoint_type_id).first()
        if not endpoint_type:
            return None
        self.db.delete(endpoint_type)
        self.db.commit()
        self.redis.delete(f"endpoint_type:{endpoint_type_id}")
        self.redis.delete("endpoint_types:all")
        return endpoint_type

    def get_all_soft_deleted(self) -> List[EndpointType]:
        return self.db.query(EndpointType).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[EndpointType]:
        try:
            result = es.search(
                index="endpoint_types",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["name", "category", "description"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["endpoint_type_id"] for hit in hits]
            return self.db.query(EndpointType).filter(EndpointType.endpoint_type_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
