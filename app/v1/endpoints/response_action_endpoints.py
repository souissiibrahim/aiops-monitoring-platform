from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.response_action import ResponseActionCreate, ResponseActionInDB, ResponseActionUpdate
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.response_action_repository import ResponseActionRepository
from app.db.models.response_action import ResponseAction
from app.services.elasticsearch.response_action_service import index_response_action

router = APIRouter()

@router.get("/", response_model=list[ResponseActionInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return ResponseActionRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[ResponseActionInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return ResponseActionRepository(db, redis).get_all_soft_deleted()

@router.get("/{action_id}", response_model=ResponseActionInDB)
def get_by_id(action_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    action = ResponseActionRepository(db, redis).get_by_id(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="ResponseAction not found")
    return action

@router.post("/", response_model=ResponseActionInDB)
def create(data: ResponseActionCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    action = ResponseActionRepository(db, redis).create(data.dict())
    index_response_action(action)
    return action

@router.put("/{action_id}", response_model=ResponseActionInDB)
def update(action_id: UUID, data: ResponseActionUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ResponseActionRepository(db, redis).update(action_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="ResponseAction not found")
    db.refresh(result)
    index_response_action(result)
    return result

@router.delete("/soft/{action_id}", response_model=ResponseActionInDB)
def soft_delete(action_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ResponseActionRepository(db, redis).soft_delete(action_id)
    if not result:
        raise HTTPException(status_code=404, detail="ResponseAction not found")
    return result

@router.put("/restore/{action_id}", response_model=ResponseActionInDB)
def restore(action_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ResponseActionRepository(db, redis).restore(action_id)
    if not result:
        raise HTTPException(status_code=404, detail="ResponseAction not found")
    return result

@router.delete("/hard/{action_id}", response_model=ResponseActionInDB)
def hard_delete(action_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ResponseActionRepository(db, redis).hard_delete(action_id)
    if not result:
        raise HTTPException(status_code=404, detail="ResponseAction not found")
    return result

@router.get("/search/{keyword}", response_model=list[ResponseActionInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return ResponseActionRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    actions = db.query(ResponseAction).filter_by(is_deleted=False).all()
    for action in actions:
        index_response_action(action)
    return {"message": f"{len(actions)} response actions indexed to Elasticsearch"}
