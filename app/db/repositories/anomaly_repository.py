from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models.anomaly import Anomaly
from typing import List, Optional


class AnomalyRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[Anomaly]:
        return self.db.query(Anomaly).filter_by(is_deleted=False).all()

    def get_by_id(self, anomaly_id: str) -> Optional[Anomaly]:
        return self.db.query(Anomaly).filter_by(anomaly_id=anomaly_id, is_deleted=False).first()

    def create(self, data: dict) -> Anomaly:
        anomaly = Anomaly(**data)
        self.db.add(anomaly)
        self.db.commit()
        self.db.refresh(anomaly)
        return anomaly

    def update(self, anomaly_id: str, update_data: dict) -> Optional[Anomaly]:
        anomaly = self.db.query(Anomaly).filter_by(anomaly_id=anomaly_id, is_deleted=False).first()
        if not anomaly:
            return None
        for key, value in update_data.items():
            setattr(anomaly, key, value)
        self.db.commit()
        self.db.refresh(anomaly)
        return anomaly

    def soft_delete(self, anomaly_id: str) -> Optional[Anomaly]:
        anomaly = self.db.query(Anomaly).filter_by(anomaly_id=anomaly_id, is_deleted=False).first()
        if not anomaly:
            return None
        anomaly.is_deleted = True
        anomaly.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"anomaly:{anomaly_id}")
        self.redis.delete("anomalies:all")
        return anomaly

    def restore(self, anomaly_id: str) -> Optional[Anomaly]:
        anomaly = self.db.query(Anomaly).filter_by(anomaly_id=anomaly_id, is_deleted=True).first()
        if not anomaly:
            return None
        anomaly.is_deleted = False
        anomaly.deleted_at = None
        self.db.commit()
        self.redis.delete(f"anomaly:{anomaly_id}")
        self.redis.delete("anomalies:all")
        return anomaly

    def hard_delete(self, anomaly_id: str) -> Optional[Anomaly]:
        anomaly = self.db.query(Anomaly).filter_by(anomaly_id=anomaly_id).first()
        if not anomaly:
            return None
        self.db.delete(anomaly)
        self.db.commit()
        self.redis.delete(f"anomaly:{anomaly_id}")
        self.redis.delete("anomalies:all")
        return anomaly

    def get_all_soft_deleted(self) -> List[Anomaly]:
        return self.db.query(Anomaly).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[Anomaly]:
        try:
            result = es.search(
                index="anomalies",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["metric_type", "detection_method"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["anomaly_id"] for hit in hits]
            return self.db.query(Anomaly).filter(Anomaly.anomaly_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
