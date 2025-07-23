from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.severity_level import SeverityLevelCreate, SeverityLevelInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.severity_level_repository import SeverityLevelRepository
from app.db.models.severity_level import SeverityLevel
from app.services.elasticsearch.severity_level_service import index_severity_level

router = APIRouter()


@router.get("/", response_model=list[SeverityLevelInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return SeverityLevelRepository(db, redis).get_all()


@router.get("/deleted", response_model=list[SeverityLevelInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return SeverityLevelRepository(db, redis).get_all_soft_deleted()


@router.get("/{severity_level_id}", response_model=SeverityLevelInDB)
def get_by_id(severity_level_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    severity_level = SeverityLevelRepository(db, redis).get_by_id(severity_level_id)
    if not severity_level:
        raise HTTPException(status_code=404, detail="Severity level not found")
    return severity_level


@router.post("/", response_model=SeverityLevelInDB)
def create(data: SeverityLevelCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    severity_level = SeverityLevelRepository(db, redis).create(data.dict())
    index_severity_level(severity_level)
    return severity_level


@router.put("/{severity_level_id}", response_model=SeverityLevelInDB)
def update(severity_level_id: UUID, data: SeverityLevelCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = SeverityLevelRepository(db, redis).update(severity_level_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Severity level not found")

    db.refresh(result)
    index_severity_level(result)
    return result


@router.delete("/soft/{severity_level_id}", response_model=SeverityLevelInDB)
def soft_delete(severity_level_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = SeverityLevelRepository(db, redis).soft_delete(severity_level_id)
    if not result:
        raise HTTPException(status_code=404, detail="Severity level not found")
    return result


@router.put("/restore/{severity_level_id}", response_model=SeverityLevelInDB)
def restore(severity_level_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = SeverityLevelRepository(db, redis).restore(severity_level_id)
    if not result:
        raise HTTPException(status_code=404, detail="Severity level not found")
    return result


@router.delete("/hard/{severity_level_id}", response_model=SeverityLevelInDB)
def hard_delete(severity_level_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = SeverityLevelRepository(db, redis).hard_delete(severity_level_id)
    if not result:
        raise HTTPException(status_code=404, detail="Severity level not found")
    return result


@router.get("/search/{keyword}", response_model=list[SeverityLevelInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return SeverityLevelRepository(db, redis).search(keyword, es)


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    severity_levels = db.query(SeverityLevel).filter_by(is_deleted=False).all()
    for severity in severity_levels:
        index_severity_level(severity)
    return {"message": f"{len(severity_levels)} severity levels indexed to Elasticsearch"}
