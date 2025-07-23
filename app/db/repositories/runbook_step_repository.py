from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.runbook_step import RunbookStep


class RunbookStepRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[RunbookStep]:
        return self.db.query(RunbookStep).filter_by(is_deleted=False).all()

    def get_by_id(self, step_id: str) -> Optional[RunbookStep]:
        return self.db.query(RunbookStep).filter_by(step_id=step_id, is_deleted=False).first()

    def create(self, step_data: dict) -> RunbookStep:
        step = RunbookStep(**step_data)
        self.db.add(step)
        self.db.commit()
        self.db.refresh(step)
        return step

    def update(self, step_id: str, update_data: dict) -> Optional[RunbookStep]:
        step = self.db.query(RunbookStep).filter_by(step_id=step_id, is_deleted=False).first()
        if not step:
            return None
        for key, value in update_data.items():
            setattr(step, key, value)
        self.db.commit()
        self.db.refresh(step)
        return step

    def soft_delete(self, step_id: str) -> Optional[RunbookStep]:
        step = self.db.query(RunbookStep).filter_by(step_id=step_id, is_deleted=False).first()
        if not step:
            return None
        step.is_deleted = True
        step.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"runbook_step:{step_id}")
        self.redis.delete("runbook_steps:all")
        return step

    def restore(self, step_id: str) -> Optional[RunbookStep]:
        step = self.db.query(RunbookStep).filter_by(step_id=step_id, is_deleted=True).first()
        if not step:
            return None
        step.is_deleted = False
        step.deleted_at = None
        self.db.commit()
        self.redis.delete(f"runbook_step:{step_id}")
        self.redis.delete("runbook_steps:all")
        return step

    def hard_delete(self, step_id: str) -> Optional[RunbookStep]:
        step = self.db.query(RunbookStep).filter_by(step_id=step_id).first()
        if not step:
            return None
        self.db.delete(step)
        self.db.commit()
        self.redis.delete(f"runbook_step:{step_id}")
        self.redis.delete("runbook_steps:all")
        return step

    def get_all_soft_deleted(self) -> List[RunbookStep]:
        return self.db.query(RunbookStep).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[RunbookStep]:
        try:
            result = es.search(
                index="runbook_steps",
                query={
                    "multi_match": {
                        "query": keyword,
                        "fields": ["description", "action_type", "command_or_script", "success_condition"],
                        "type": "best_fields"
                    }
                }
            )
            hits = result["hits"]["hits"]
            ids = [hit["_source"]["step_id"] for hit in hits]
            return self.db.query(RunbookStep).filter(RunbookStep.step_id.in_(ids)).all()
        except Exception as e:
            print(f"❌ Elasticsearch search failed: {e}")
            raise
