from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.audit_log import AuditLogCreate, AuditLogInDB, AuditLogUpdate
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.audit_log_repository import AuditLogRepository
from app.db.models.audit_log import AuditLog
from app.services.elasticsearch.audit_log_service import index_audit_log
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    logs = AuditLogRepository(db, redis).get_all()
    return success_response(serialize(logs, AuditLogInDB), "Audit logs fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    logs = AuditLogRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(logs, AuditLogInDB), "Soft deleted audit logs fetched successfully.")


@router.get("/{log_id}")
def get_by_id(log_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    log = AuditLogRepository(db, redis).get_by_id(log_id)
    if not log:
        return error_response("Audit log not found", 404)
    return success_response(serialize(log, AuditLogInDB), "Audit log fetched successfully.")


@router.post("/")
def create(data: AuditLogCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    log = AuditLogRepository(db, redis).create(data.dict())
    try:
        index_audit_log(log)
    except Exception as e:
        print(f"❌ Failed to index audit log after creation: {e}")
    return success_response(serialize(log, AuditLogInDB), "Audit log created successfully.", 201)


@router.put("/{log_id}")
def update(log_id: UUID, data: AuditLogUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AuditLogRepository(db, redis).update(log_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Audit log not found", 404)
    try:
        db.refresh(result)
        index_audit_log(result)
    except Exception as e:
        print(f"❌ Failed to reindex audit log after update: {e}")
    return success_response(serialize(result, AuditLogInDB), "Audit log updated successfully.")


@router.delete("/soft/{log_id}")
def soft_delete(log_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AuditLogRepository(db, redis).soft_delete(log_id)
    if not result:
        return error_response("Audit log not found", 404)
    return success_response(serialize(result, AuditLogInDB), "Audit log soft deleted successfully.")


@router.put("/restore/{log_id}")
def restore(log_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AuditLogRepository(db, redis).restore(log_id)
    if not result:
        return error_response("Audit log not found", 404)
    return success_response(serialize(result, AuditLogInDB), "Audit log restored successfully.")


@router.delete("/hard/{log_id}")
def hard_delete(log_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AuditLogRepository(db, redis).hard_delete(log_id)
    if not result:
        return error_response("Audit log not found", 404)
    return success_response(serialize(result, AuditLogInDB), "Audit log permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = AuditLogRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, AuditLogInDB), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    logs = db.query(AuditLog).filter_by(is_deleted=False).all()
    count = 0
    for log in logs:
        try:
            index_audit_log(log)
            count += 1
        except Exception as e:
            print(f"❌ Failed to index audit log {log.id}: {e}")
    return success_response({"count": count}, "All audit logs indexed to Elasticsearch.")
