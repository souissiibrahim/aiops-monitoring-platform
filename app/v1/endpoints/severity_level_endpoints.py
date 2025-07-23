from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.severity_level import SeverityLevelCreate, SeverityLevelInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.severity_level_repository import SeverityLevelRepository
from app.db.models.severity_level import SeverityLevel
from app.services.elasticsearch.severity_level_service import index_severity_level
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    severity_levels = SeverityLevelRepository(db, redis).get_all()
    return success_response(serialize(severity_levels, SeverityLevelInDB), "Severity levels fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    severity_levels = SeverityLevelRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(severity_levels, SeverityLevelInDB), "Soft deleted severity levels fetched successfully.")


@router.get("/{severity_level_id}")
def get_by_id(severity_level_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    severity_level = SeverityLevelRepository(db, redis).get_by_id(severity_level_id)
    if not severity_level:
        return error_response("Severity level not found", 404)
    return success_response(serialize(severity_level, SeverityLevelInDB), "Severity level fetched successfully.")


@router.post("/")
def create(data: SeverityLevelCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    severity_level = SeverityLevelRepository(db, redis).create(data.dict())
    index_severity_level(severity_level)
    return success_response(serialize(severity_level, SeverityLevelInDB), "Severity level created successfully.", 201)


@router.put("/{severity_level_id}")
def update(severity_level_id: UUID, data: SeverityLevelCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = SeverityLevelRepository(db, redis).update(severity_level_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Severity level not found", 404)
    db.refresh(result)
    index_severity_level(result)
    return success_response(serialize(result, SeverityLevelInDB), "Severity level updated successfully.")


@router.delete("/soft/{severity_level_id}")
def soft_delete(severity_level_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = SeverityLevelRepository(db, redis).soft_delete(severity_level_id)
    if not result:
        return error_response("Severity level not found", 404)
    return success_response(serialize(result, SeverityLevelInDB), "Severity level soft deleted successfully.")


@router.put("/restore/{severity_level_id}")
def restore(severity_level_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = SeverityLevelRepository(db, redis).restore(severity_level_id)
    if not result:
        return error_response("Severity level not found", 404)
    return success_response(serialize(result, SeverityLevelInDB), "Severity level restored successfully.")


@router.delete("/hard/{severity_level_id}")
def hard_delete(severity_level_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = SeverityLevelRepository(db, redis).hard_delete(severity_level_id)
    if not result:
        return error_response("Severity level not found", 404)
    return success_response(serialize(result, SeverityLevelInDB), "Severity level permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = SeverityLevelRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, SeverityLevelInDB), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    severity_levels = db.query(SeverityLevel).filter_by(is_deleted=False).all()
    for severity in severity_levels:
        index_severity_level(severity)
    return success_response({"count": len(severity_levels)}, "All severity levels indexed to Elasticsearch.")
