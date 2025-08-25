from sqlalchemy.orm import Session
from sqlalchemy import func, text
from typing import List, Optional
from app.db.models.prediction import Prediction

class PredictionRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[Prediction]:
        return self.db.query(Prediction).filter_by(is_deleted=False).all()

    def get_by_id(self, prediction_id: str) -> Optional[Prediction]:
        return self.db.query(Prediction).filter_by(prediction_id=prediction_id, is_deleted=False).first()

    def create(self, data: dict) -> Prediction:
        prediction = Prediction(**data)
        self.db.add(prediction)
        self.db.commit()
        self.db.refresh(prediction)
        return prediction

    def update(self, prediction_id: str, update_data: dict) -> Optional[Prediction]:
        prediction = self.db.query(Prediction).filter_by(prediction_id=prediction_id, is_deleted=False).first()
        if not prediction:
            return None

        for key, value in update_data.items():
            setattr(prediction, key, value)

        self.db.commit()
        self.db.refresh(prediction)
        return prediction

    def soft_delete(self, prediction_id: str) -> Optional[Prediction]:
        prediction = self.db.query(Prediction).filter_by(prediction_id=prediction_id, is_deleted=False).first()
        if not prediction:
            return None

        prediction.is_deleted = True
        prediction.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"prediction:{prediction_id}")
        self.redis.delete("predictions:all")
        return prediction

    def restore(self, prediction_id: str) -> Optional[Prediction]:
        prediction = self.db.query(Prediction).filter_by(prediction_id=prediction_id, is_deleted=True).first()
        if not prediction:
            return None

        prediction.is_deleted = False
        prediction.deleted_at = None
        self.db.commit()
        self.redis.delete(f"prediction:{prediction_id}")
        self.redis.delete("predictions:all")
        return prediction

    def hard_delete(self, prediction_id: str) -> Optional[Prediction]:
        prediction = self.db.query(Prediction).filter_by(prediction_id=prediction_id).first()
        if not prediction:
            return None

        self.db.delete(prediction)
        self.db.commit()
        self.redis.delete(f"prediction:{prediction_id}")
        self.redis.delete("predictions:all")
        return prediction

    def get_all_soft_deleted(self) -> List[Prediction]:
        return self.db.query(Prediction).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[Prediction]:
        try:
            result = es.search(
                index="predictions",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["status"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["prediction_id"] for hit in hits]
            return self.db.query(Prediction).filter(Prediction.prediction_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch Prediction search failed: {e}")
            raise

    def link_nearest_pending(
        self,
        *,
        incident_id: str,
        instance: str,
        incident_type: str,
        severity: str,
        start_ts_utc_iso: str,  # e.g. "2025-08-16T09:40:00Z"
        window_sec: int = 300,   # ±5 minutes (tune via env)
    ) -> Optional[str]:
        """
        Find the nearest Pending prediction that matches (instance, incident_type, severity)
        within ±window_sec of start_ts_utc_iso, then set incident_id and mark as Confirmed.
        Returns the linked prediction_id or None.
        """
        sql = text("""
        WITH cand AS (
          SELECT p.prediction_id
          FROM predictions p
          WHERE p.is_deleted = FALSE
            AND p.status = 'Pending'
            AND p.input_features->>'instance' = :instance
            AND p.prediction_output->>'incident_type_name' = :itype
            AND p.prediction_output->>'severity_name' = :sev
            AND ABS(EXTRACT(EPOCH FROM (
                  ((p.input_features->>'forecast_for')::timestamptz) - (:start_ts)::timestamptz
                ))) <= :window_sec
          ORDER BY ABS(EXTRACT(EPOCH FROM (
                    ((p.input_features->>'forecast_for')::timestamptz) - (:start_ts)::timestamptz
                  )))
          LIMIT 1
        )
        UPDATE predictions p
        SET incident_id = :incident_id,
            status = 'Confirmed',
            updated_at = NOW()
        FROM cand
        WHERE p.prediction_id = cand.prediction_id
        RETURNING p.prediction_id
        """)
        row = self.db.execute(sql, {
            "incident_id": incident_id,
            "instance": instance,
            "itype": incident_type,
            "sev": severity,
            "start_ts": start_ts_utc_iso,
            "window_sec": window_sec
        }).fetchone()
        self.db.commit()
        return row[0] if row else None
