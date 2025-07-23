from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.runbook import RunbookCreate, RunbookUpdate, RunbookInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.runbook_repository import RunbookRepository
from app.db.models.runbook import Runbook
from app.services.elasticsearch.runbook_service import index_runbook
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbooks = RunbookRepository(db, redis).get_all()
    return success_response(serialize(runbooks, RunbookInDB), "Runbooks fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbooks = RunbookRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(runbooks, RunbookInDB), "Soft deleted runbooks fetched successfully.")


@router.get("/{runbook_id}")
def get_by_id(runbook_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbook = RunbookRepository(db, redis).get_by_id(runbook_id)
    if not runbook:
        return error_response("Runbook not found", 404)
    return success_response(serialize(runbook, RunbookInDB), "Runbook fetched successfully.")


@router.post("/")
def create(data: RunbookCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbook = RunbookRepository(db, redis).create(data.dict())
    index_runbook(runbook)
    return success_response(serialize(runbook, RunbookInDB), "Runbook created successfully.", 201)


@router.put("/{runbook_id}")
def update(runbook_id: UUID, data: RunbookUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RunbookRepository(db, redis).update(runbook_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Runbook not found", 404)
    db.refresh(result)
    index_runbook(result)
    return success_response(serialize(result, RunbookInDB), "Runbook updated successfully.")


@router.delete("/soft/{runbook_id}")
def soft_delete(runbook_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RunbookRepository(db, redis).soft_delete(runbook_id)
    if not result:
        return error_response("Runbook not found", 404)
    return success_response(serialize(result, RunbookInDB), "Runbook soft deleted successfully.")


@router.put("/restore/{runbook_id}")
def restore(runbook_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RunbookRepository(db, redis).restore(runbook_id)
    if not result:
        return error_response("Runbook not found", 404)
    return success_response(serialize(result, RunbookInDB), "Runbook restored successfully.")


@router.delete("/hard/{runbook_id}")
def hard_delete(runbook_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RunbookRepository(db, redis).hard_delete(runbook_id)
    if not result:
        return error_response("Runbook not found", 404)
    return success_response(serialize(result, RunbookInDB), "Runbook permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = RunbookRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, RunbookInDB), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    runbooks = db.query(Runbook).filter_by(is_deleted=False).all()
    for runbook in runbooks:
        index_runbook(runbook)
    return success_response({"count": len(runbooks)}, "All runbooks indexed to Elasticsearch.")
