from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional

from app.db.models.team_endpoint_ownership import TeamEndpointOwnership


class TeamEndpointOwnershipRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[TeamEndpointOwnership]:
        return self.db.query(TeamEndpointOwnership).filter_by(is_deleted=False).all()

    def get_by_id(self, ownership_id: str) -> Optional[TeamEndpointOwnership]:
        return self.db.query(TeamEndpointOwnership).filter_by(ownership_id=ownership_id, is_deleted=False).first()

    def create(self, ownership_data: dict) -> TeamEndpointOwnership:
        ownership = TeamEndpointOwnership(**ownership_data)
        self.db.add(ownership)
        self.db.commit()
        self.db.refresh(ownership)
        return ownership

    def update(self, ownership_id: str, update_data: dict) -> Optional[TeamEndpointOwnership]:
        ownership = self.db.query(TeamEndpointOwnership).filter_by(ownership_id=ownership_id, is_deleted=False).first()
        if not ownership:
            return None

        for key, value in update_data.items():
            setattr(ownership, key, value)

        self.db.commit()
        self.db.refresh(ownership)
        return ownership

    def soft_delete(self, ownership_id: str) -> Optional[TeamEndpointOwnership]:
        ownership = self.db.query(TeamEndpointOwnership).filter_by(ownership_id=ownership_id, is_deleted=False).first()
        if not ownership:
            return None

        ownership.is_deleted = True
        ownership.deleted_at = func.now()
        self.db.commit()

        self.redis.delete(f"team_endpoint_ownership:{ownership_id}")
        self.redis.delete("team_endpoint_ownerships:all")
        return ownership

    def restore(self, ownership_id: str) -> Optional[TeamEndpointOwnership]:
        ownership = self.db.query(TeamEndpointOwnership).filter_by(ownership_id=ownership_id, is_deleted=True).first()
        if not ownership:
            return None

        ownership.is_deleted = False
        ownership.deleted_at = None
        self.db.commit()

        self.redis.delete(f"team_endpoint_ownership:{ownership_id}")
        self.redis.delete("team_endpoint_ownerships:all")
        return ownership

    def hard_delete(self, ownership_id: str) -> Optional[TeamEndpointOwnership]:
        ownership = self.db.query(TeamEndpointOwnership).filter_by(ownership_id=ownership_id).first()
        if not ownership:
            return None

        self.db.delete(ownership)
        self.db.commit()

        self.redis.delete(f"team_endpoint_ownership:{ownership_id}")
        self.redis.delete("team_endpoint_ownerships:all")
        return ownership

    def get_all_soft_deleted(self) -> List[TeamEndpointOwnership]:
        return self.db.query(TeamEndpointOwnership).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[TeamEndpointOwnership]:
        try:
            result = es.search(
                index="team_endpoint_ownerships",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["is_primary"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["ownership_id"] for hit in hits]
            return self.db.query(TeamEndpointOwnership).filter(TeamEndpointOwnership.ownership_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
