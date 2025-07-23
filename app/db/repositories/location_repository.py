from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models.location import Location
from typing import List, Optional


class LocationRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[Location]:
        return self.db.query(Location).filter_by(is_deleted=False).all()

    def get_by_id(self, location_id: str) -> Optional[Location]:
        return self.db.query(Location).filter_by(location_id=location_id, is_deleted=False).first()

    def create(self, data: dict) -> Location:
        location = Location(**data)
        self.db.add(location)
        self.db.commit()
        self.db.refresh(location)
        return location

    def update(self, location_id: str, update_data: dict) -> Optional[Location]:
        location = self.db.query(Location).filter_by(location_id=location_id, is_deleted=False).first()
        if not location:
            return None
        for key, value in update_data.items():
            setattr(location, key, value)
        self.db.commit()
        self.db.refresh(location)
        return location

    def soft_delete(self, location_id: str) -> Optional[Location]:
        location = self.db.query(Location).filter_by(location_id=location_id, is_deleted=False).first()
        if not location:
            return None
        location.is_deleted = True
        location.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"location:{location_id}")
        self.redis.delete("locations:all")
        return location

    def restore(self, location_id: str) -> Optional[Location]:
        location = self.db.query(Location).filter_by(location_id=location_id, is_deleted=True).first()
        if not location:
            return None
        location.is_deleted = False
        location.deleted_at = None
        self.db.commit()
        self.redis.delete(f"location:{location_id}")
        self.redis.delete("locations:all")
        return location

    def hard_delete(self, location_id: str) -> Optional[Location]:
        location = self.db.query(Location).filter_by(location_id=location_id).first()
        if not location:
            return None
        self.db.delete(location)
        self.db.commit()
        self.redis.delete(f"location:{location_id}")
        self.redis.delete("locations:all")
        return location

    def get_all_soft_deleted(self) -> List[Location]:
        return self.db.query(Location).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[Location]:
        try:
            result = es.search(
                index="locations",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["name", "region_code", "country"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["location_id"] for hit in hits]
            return self.db.query(Location).filter(Location.location_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
