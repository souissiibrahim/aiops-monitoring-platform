from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.rca_analysis import RCAAnalysis

class RCAAnalysisRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[RCAAnalysis]:
        return self.db.query(RCAAnalysis).filter_by(is_deleted=False).all()

    def get_by_id(self, rca_id: str) -> Optional[RCAAnalysis]:
        return self.db.query(RCAAnalysis).filter_by(rca_id=rca_id, is_deleted=False).first()

    def create(self, rca_data: dict) -> RCAAnalysis:
        rca = RCAAnalysis(**rca_data)
        self.db.add(rca)
        self.db.commit()
        self.db.refresh(rca)
        return rca

    def update(self, rca_id: str, update_data: dict) -> Optional[RCAAnalysis]:
        rca = self.db.query(RCAAnalysis).filter_by(rca_id=rca_id, is_deleted=False).first()
        if not rca:
            return None
        for key, value in update_data.items():
            setattr(rca, key, value)
        self.db.commit()
        self.db.refresh(rca)
        return rca

    def soft_delete(self, rca_id: str) -> Optional[RCAAnalysis]:
        rca = self.db.query(RCAAnalysis).filter_by(rca_id=rca_id, is_deleted=False).first()
        if not rca:
            return None
        rca.is_deleted = True
        rca.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"rca:{rca_id}")
        self.redis.delete("rca:all")
        return rca

    def restore(self, rca_id: str) -> Optional[RCAAnalysis]:
        rca = self.db.query(RCAAnalysis).filter_by(rca_id=rca_id, is_deleted=True).first()
        if not rca:
            return None
        rca.is_deleted = False
        rca.deleted_at = None
        self.db.commit()
        self.redis.delete(f"rca:{rca_id}")
        self.redis.delete("rca:all")
        return rca

    def hard_delete(self, rca_id: str) -> Optional[RCAAnalysis]:
        rca = self.db.query(RCAAnalysis).filter_by(rca_id=rca_id).first()
        if not rca:
            return None
        self.db.delete(rca)
        self.db.commit()
        self.redis.delete(f"rca:{rca_id}")
        self.redis.delete("rca:all")
        return rca

    def get_all_soft_deleted(self) -> List[RCAAnalysis]:
        return self.db.query(RCAAnalysis).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[RCAAnalysis]:
        try:
            result = es.search(
                index="rca_analysis",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["analysis_method", "recommendations"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["rca_id"] for hit in hits]
            return self.db.query(RCAAnalysis).filter(RCAAnalysis.rca_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch RCA search failed: {e}")
            raise
