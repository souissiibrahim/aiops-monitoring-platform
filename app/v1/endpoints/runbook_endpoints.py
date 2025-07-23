from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.runbook import RunbookCreate, RunbookUpdate, RunbookInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.runbook_repository import RunbookRepository
from app.db.models.runbook import Runbook
from app.services.elasticsearch.runbook_service import index_runbook

router = APIRouter()

@router.get("/", response_model=list[RunbookInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return RunbookRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[RunbookInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return RunbookRepository(db, redis).get_all_soft_deleted()

@router.get("/{runbook_id}", response_model=RunbookInDB)
def get_by_id(runbook_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbook = RunbookRepository(db, redis).get_by_id(runbook_id)
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")
    return runbook

@router.post("/", response_model=RunbookInDB)
def create(data: RunbookCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbook = RunbookRepository(db, redis).create(data.dict())
    index_runbook(runbook)
    return runbook

@router.put("/{runbook_id}", response_model=RunbookInDB)
def update(runbook_id: UUID, data: RunbookUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbook = RunbookRepository(db, redis).update(runbook_id, data.dict(exclude_unset=True))
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")
    db.refresh(runbook)
    index_runbook(runbook)
    return runbook

@router.delete("/soft/{runbook_id}", response_model=RunbookInDB)
def soft_delete(runbook_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbook = RunbookRepository(db, redis).soft_delete(runbook_id)
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")
    return runbook

@router.put("/restore/{runbook_id}", response_model=RunbookInDB)
def restore(runbook_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbook = RunbookRepository(db, redis).restore(runbook_id)
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")
    return runbook

@router.delete("/hard/{runbook_id}", response_model=RunbookInDB)
def hard_delete(runbook_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    runbook = RunbookRepository(db, redis).hard_delete(runbook_id)
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")
    return runbook

@router.get("/search/{keyword}", response_model=list[RunbookInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return RunbookRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    runbooks = db.query(Runbook).filter_by(is_deleted=False).all()
    for runbook in runbooks:
        index_runbook(runbook)
    return {"message": f"{len(runbooks)} runbooks indexed to Elasticsearch"}
