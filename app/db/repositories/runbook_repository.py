from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.runbook import Runbook


class RunbookRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[Runbook]:
        return self.db.query(Runbook).filter_by(is_deleted=False).all()

    def get_by_id(self, runbook_id: str) -> Optional[Runbook]:
        return self.db.query(Runbook).filter_by(runbook_id=runbook_id, is_deleted=False).first()

    def create(self, runbook_data: dict) -> Runbook:
        runbook = Runbook(**runbook_data)
        self.db.add(runbook)
        self.db.commit()
        self.db.refresh(runbook)
        return runbook

    def update(self, runbook_id: str, update_data: dict) -> Optional[Runbook]:
        runbook = self.db.query(Runbook).filter_by(runbook_id=runbook_id, is_deleted=False).first()
        if not runbook:
            return None
        for key, value in update_data.items():
            setattr(runbook, key, value)
        self.db.commit()
        self.db.refresh(runbook)
        return runbook

    def soft_delete(self, runbook_id: str) -> Optional[Runbook]:
        runbook = self.db.query(Runbook).filter_by(runbook_id=runbook_id, is_deleted=False).first()
        if not runbook:
            return None
        runbook.is_deleted = True
        runbook.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"runbook:{runbook_id}")
        self.redis.delete("runbooks:all")
        return runbook

    def restore(self, runbook_id: str) -> Optional[Runbook]:
        runbook = self.db.query(Runbook).filter_by(runbook_id=runbook_id, is_deleted=True).first()
        if not runbook:
            return None
        runbook.is_deleted = False
        runbook.deleted_at = None
        self.db.commit()
        self.redis.delete(f"runbook:{runbook_id}")
        self.redis.delete("runbooks:all")
        return runbook

    def hard_delete(self, runbook_id: str) -> Optional[Runbook]:
        runbook = self.db.query(Runbook).filter_by(runbook_id=runbook_id).first()
        if not runbook:
            return None
        self.db.delete(runbook)
        self.db.commit()
        self.redis.delete(f"runbook:{runbook_id}")
        self.redis.delete("runbooks:all")
        return runbook

    def get_all_soft_deleted(self) -> List[Runbook]:
        return self.db.query(Runbook).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[Runbook]:
        try:
            result = es.search(
                index="runbooks",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["name", "description"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["runbook_id"] for hit in hits]
            return self.db.query(Runbook).filter(Runbook.runbook_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
