from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from app.db.models.response_action import ResponseAction


class ResponseActionRepository:
    def __init__(self, db: Session, redis):
        self.db = db
        self.redis = redis

    def get_all(self) -> List[ResponseAction]:
        return self.db.query(ResponseAction).filter_by(is_deleted=False).all()

    def get_by_id(self, action_id: str) -> Optional[ResponseAction]:
        return self.db.query(ResponseAction).filter_by(action_id=action_id, is_deleted=False).first()

    def create(self, data: dict) -> ResponseAction:
        response_action = ResponseAction(**data)
        self.db.add(response_action)
        self.db.commit()
        self.db.refresh(response_action)
        return response_action

    def update(self, action_id: str, update_data: dict) -> Optional[ResponseAction]:
        response_action = self.get_by_id(action_id)
        if not response_action:
            return None
        for key, value in update_data.items():
            setattr(response_action, key, value)
        self.db.commit()
        self.db.refresh(response_action)
        return response_action

    def soft_delete(self, action_id: str) -> Optional[ResponseAction]:
        response_action = self.get_by_id(action_id)
        if not response_action:
            return None
        response_action.is_deleted = True
        response_action.deleted_at = func.now()
        self.db.commit()
        self.redis.delete(f"response_action:{action_id}")
        self.redis.delete("response_actions:all")
        return response_action

    def restore(self, action_id: str) -> Optional[ResponseAction]:
        response_action = self.db.query(ResponseAction).filter_by(action_id=action_id, is_deleted=True).first()
        if not response_action:
            return None
        response_action.is_deleted = False
        response_action.deleted_at = None
        self.db.commit()
        self.redis.delete(f"response_action:{action_id}")
        self.redis.delete("response_actions:all")
        return response_action

    def hard_delete(self, action_id: str) -> Optional[ResponseAction]:
        response_action = self.db.query(ResponseAction).filter_by(action_id=action_id).first()
        if not response_action:
            return None
        self.db.delete(response_action)
        self.db.commit()
        self.redis.delete(f"response_action:{action_id}")
        self.redis.delete("response_actions:all")
        return response_action

    def get_all_soft_deleted(self) -> List[ResponseAction]:
        return self.db.query(ResponseAction).filter_by(is_deleted=True).all()

    def search(self, keyword: str, es) -> List[dict]:
        try:
            query = {
                "query": {
                    "multi_match": {
                        "query": keyword,
                        "fields": ["execution_log", "status", "error_message"]
                    }
                }
            }
            result = es.search(index="response_actions", body=query)
            return [hit["_source"] for hit in result["hits"]["hits"]]
        except Exception as e:
            print(f"[Elasticsearch] Search failed: {str(e)}")
            return []
