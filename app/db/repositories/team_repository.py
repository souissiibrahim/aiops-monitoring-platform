from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.team import Team


class TeamRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[Team]:
        return self.db.query(Team).filter_by(is_deleted=False).all()

    def get_by_id(self, team_id: str) -> Optional[Team]:
        return self.db.query(Team).filter_by(team_id=team_id, is_deleted=False).first()

    def create(self, team_data: dict) -> Team:
        team = Team(**team_data)
        self.db.add(team)
        self.db.commit()
        self.db.refresh(team)
        return team

    def update(self, team_id: str, update_data: dict) -> Optional[Team]:
        team = self.db.query(Team).filter_by(team_id=team_id, is_deleted=False).first()
        if not team:
            return None
        for key, value in update_data.items():
            setattr(team, key, value)
        self.db.commit()
        self.db.refresh(team)
        return team

    def soft_delete(self, team_id: str) -> Optional[Team]:
        team = self.db.query(Team).filter_by(team_id=team_id, is_deleted=False).first()
        if not team:
            return None
        team.is_deleted = True
        team.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"team:{team_id}")
        self.redis.delete("teams:all")
        return team

    def restore(self, team_id: str) -> Optional[Team]:
        team = self.db.query(Team).filter_by(team_id=team_id, is_deleted=True).first()
        if not team:
            return None
        team.is_deleted = False
        team.deleted_at = None
        self.db.commit()
        self.redis.delete(f"team:{team_id}")
        self.redis.delete("teams:all")
        return team

    def hard_delete(self, team_id: str) -> Optional[Team]:
        team = self.db.query(Team).filter_by(team_id=team_id).first()
        if not team:
            return None
        self.db.delete(team)
        self.db.commit()
        self.redis.delete(f"team:{team_id}")
        self.redis.delete("teams:all")
        return team

    def get_all_soft_deleted(self) -> List[Team]:
        return self.db.query(Team).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[Team]:
        try:
            result = es.search(
                index="teams",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["name", "description", "contact_email", "slack_channel"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["team_id"] for hit in hits]
            return self.db.query(Team).filter(Team.team_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
