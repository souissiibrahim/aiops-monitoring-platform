from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.audit_log import AuditLogCreate, AuditLogInDB, AuditLogUpdate
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.audit_log_repository import AuditLogRepository
from app.db.models.audit_log import AuditLog
from app.services.elasticsearch.audit_log_service import index_audit_log

router = APIRouter()

@router.get("/", response_model=list[AuditLogInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return AuditLogRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[AuditLogInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return AuditLogRepository(db, redis).get_all_soft_deleted()

@router.get("/{log_id}", response_model=AuditLogInDB)
def get_by_id(log_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    log = AuditLogRepository(db, redis).get_by_id(log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return log

@router.post("/", response_model=AuditLogInDB)
def create(data: AuditLogCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    log = AuditLogRepository(db, redis).create(data.dict())
    index_audit_log(log)
    return log

@router.put("/{log_id}", response_model=AuditLogInDB)
def update(log_id: UUID, data: AuditLogUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AuditLogRepository(db, redis).update(log_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Audit log not found")
    
    db.refresh(result)
    index_audit_log(result)
    return result

@router.delete("/soft/{log_id}", response_model=AuditLogInDB)
def soft_delete(log_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AuditLogRepository(db, redis).soft_delete(log_id)
    if not result:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return result

@router.put("/restore/{log_id}", response_model=AuditLogInDB)
def restore(log_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AuditLogRepository(db, redis).restore(log_id)
    if not result:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return result

@router.delete("/hard/{log_id}", response_model=AuditLogInDB)
def hard_delete(log_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AuditLogRepository(db, redis).hard_delete(log_id)
    if not result:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return result

@router.get("/search/{keyword}", response_model=list[AuditLogInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return AuditLogRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    logs = db.query(AuditLog).filter_by(is_deleted=False).all()
    for log in logs:
        index_audit_log(log)
    return {"message": f"{len(logs)} audit logs indexed to Elasticsearch"}
