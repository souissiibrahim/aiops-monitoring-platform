from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.v1.schemas.log_entry_schemas import LogEntryCreate, LogEntryUpdate, LogEntryOut
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.log_entry_repository import LogEntryRepository
from app.db.models.log_entry import LogEntry
from app.services.elasticsearch.log_entry_service import index_log_entry  # Optional if you plan to implement this

router = APIRouter()


@router.get("/", response_model=list[LogEntryOut])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return LogEntryRepository(db, redis).get_all()


@router.get("/deleted", response_model=list[LogEntryOut])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return LogEntryRepository(db, redis).get_all_soft_deleted()


@router.get("/{log_id}", response_model=LogEntryOut)
def get_by_id(log_id: int, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    entry = LogEntryRepository(db, redis).get_by_id(log_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return entry


@router.post("/", response_model=LogEntryOut)
def create(data: LogEntryCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    entry = LogEntryRepository(db, redis).create(data.dict())
    index_log_entry(entry)  # Optional: call only if you’ve implemented the ES indexing
    return entry


@router.put("/{log_id}", response_model=LogEntryOut)
def update(log_id: int, data: LogEntryUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = LogEntryRepository(db, redis).update(log_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Log entry not found")

    db.refresh(result)
    index_log_entry(result)  # Optional
    return result


@router.delete("/soft/{log_id}", response_model=LogEntryOut)
def soft_delete(log_id: int, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = LogEntryRepository(db, redis).soft_delete(log_id)
    if not result:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return result


@router.put("/restore/{log_id}", response_model=LogEntryOut)
def restore(log_id: int, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = LogEntryRepository(db, redis).restore(log_id)
    if not result:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return result


@router.delete("/hard/{log_id}", response_model=LogEntryOut)
def hard_delete(log_id: int, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = LogEntryRepository(db, redis).hard_delete(log_id)
    if not result:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return result


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    entries = db.query(LogEntry).filter_by(is_deleted=False).all()
    for entry in entries:
        index_log_entry(entry)
    return {"message": f"{len(entries)} log entries indexed to Elasticsearch"}


@router.get("/search/{keyword}", response_model=list[LogEntryOut])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return LogEntryRepository(db, redis).search(keyword, es)
