from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.rca_report import RCAReport
from fastapi import HTTPException


class RCAReportRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[RCAReport]:
        return self.db.query(RCAReport).filter_by(is_deleted=False).all()

    def get_by_id(self, rca_id: int) -> Optional[RCAReport]:
        return self.db.query(RCAReport).filter_by(id=rca_id, is_deleted=False).first()

    def create(self, rca_data: dict) -> RCAReport:
        rca_report = RCAReport(**rca_data)
        self.db.add(rca_report)
        self.db.commit()
        self.db.refresh(rca_report)
        return rca_report

    def update(self, rca_id: int, update_data: dict) -> Optional[RCAReport]:
        rca_report = self.db.query(RCAReport).filter_by(id=rca_id, is_deleted=False).first()
        if not rca_report:
            return None

        for key, value in update_data.items():
            setattr(rca_report, key, value)

        self.db.commit()
        self.db.refresh(rca_report)
        return rca_report

    def soft_delete(self, rca_id: int) -> Optional[RCAReport]:
        rca_report = self.db.query(RCAReport).filter_by(id=rca_id, is_deleted=False).first()
        if not rca_report:
            return None

        rca_report.is_deleted = True
        rca_report.deleted_at = func.now()
        self.db.commit()

        self.redis.delete(f"rca:{rca_id}")
        self.redis.delete("rcas:all")
        return rca_report

    def restore(self, rca_id: int) -> Optional[RCAReport]:
        rca_report = self.db.query(RCAReport).filter_by(id=rca_id, is_deleted=True).first()
        if not rca_report:
            return None

        rca_report.is_deleted = False
        rca_report.deleted_at = None
        self.db.commit()

        self.redis.delete(f"rca:{rca_id}")
        self.redis.delete("rcas:all")
        return rca_report

    def hard_delete(self, rca_id: int) -> Optional[RCAReport]:
        rca_report = self.db.query(RCAReport).filter_by(id=rca_id).first()
        if not rca_report:
            return None

        self.db.delete(rca_report)
        self.db.commit()

        self.redis.delete(f"rca:{rca_id}")
        self.redis.delete("rcas:all")
        return rca_report

    def get_all_soft_deleted(self) -> List[RCAReport]:
        return self.db.query(RCAReport).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[RCAReport]:
        try:
            result = es.search(
                index="rca_reports",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["root_cause", "recommendation"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [int(hit["_source"]["id"]) for hit in hits]
            return self.db.query(RCAReport).filter(RCAReport.id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise HTTPException(status_code=500, detail="Elasticsearch search error")
