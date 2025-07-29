from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.response_action import ResponseActionCreate, ResponseActionRead, ResponseActionUpdate
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.response_action_repository import ResponseActionRepository
from app.db.models.response_action import ResponseAction
from app.services.elasticsearch.response_action_service import index_response_action
from app.utils.response import success_response, error_response

router = APIRouter()

def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    actions = ResponseActionRepository(db, redis).get_all()
    return success_response(serialize(actions, ResponseActionRead), "Response actions fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    actions = ResponseActionRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(actions, ResponseActionRead), "Soft deleted response actions fetched successfully.")

@router.get("/count/running")
def count_running_response_actions(db: Session = Depends(get_db)):
    count = db.query(ResponseAction).filter(
        ResponseAction.status.in_(["Pending", "In Progress"]),
        ResponseAction.is_deleted == False
    ).count()
    return success_response({"running_now": count}, "Running response actions counted.")


@router.get("/{action_id}")
def get_by_id(action_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    action = ResponseActionRepository(db, redis).get_by_id(action_id)
    if not action:
        return error_response("Response action not found", 404)
    return success_response(serialize(action, ResponseActionRead), "Response action fetched successfully.")


@router.post("/")
def create(data: ResponseActionCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    action = ResponseActionRepository(db, redis).create(data.dict())
    try:
        index_response_action(action)
    except Exception as e:
        print(f"❌ Failed to index response action: {e}")
    return success_response(serialize(action, ResponseActionRead), "Response action created successfully.", 201)


@router.put("/{action_id}")
def update(action_id: UUID, data: ResponseActionUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ResponseActionRepository(db, redis).update(action_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Response action not found", 404)
    try:
        db.refresh(result)
        index_response_action(result)
    except Exception as e:
        print(f"❌ Failed to reindex response action: {e}")
    return success_response(serialize(result, ResponseActionRead), "Response action updated successfully.")


@router.delete("/soft/{action_id}")
def soft_delete(action_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ResponseActionRepository(db, redis).soft_delete(action_id)
    if not result:
        return error_response("Response action not found", 404)
    return success_response(serialize(result, ResponseActionRead), "Response action soft deleted successfully.")


@router.put("/restore/{action_id}")
def restore(action_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ResponseActionRepository(db, redis).restore(action_id)
    if not result:
        return error_response("Response action not found", 404)
    return success_response(serialize(result, ResponseActionRead), "Response action restored successfully.")


@router.delete("/hard/{action_id}")
def hard_delete(action_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ResponseActionRepository(db, redis).hard_delete(action_id)
    if not result:
        return error_response("Response action not found", 404)
    return success_response(serialize(result, ResponseActionRead), "Response action permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = ResponseActionRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, ResponseActionRead), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    actions = db.query(ResponseAction).filter_by(is_deleted=False).all()
    count = 0
    for action in actions:
        try:
            index_response_action(action)
            count += 1
        except Exception as e:
            print(f"❌ Failed to index response action {action.id}: {e}")
    return success_response({"count": count}, "All response actions indexed to Elasticsearch.")
