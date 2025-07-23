from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.runbook_step import RunbookStepCreate, RunbookStepUpdate, RunbookStepInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.runbook_step_repository import RunbookStepRepository
from app.db.models.runbook_step import RunbookStep
from app.services.elasticsearch.runbook_step_service import index_runbook_step

router = APIRouter()

@router.get("/", response_model=list[RunbookStepInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return RunbookStepRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[RunbookStepInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return RunbookStepRepository(db, redis).get_all_soft_deleted()

@router.get("/{step_id}", response_model=RunbookStepInDB)
def get_by_id(step_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    step = RunbookStepRepository(db, redis).get_by_id(step_id)
    if not step:
        raise HTTPException(status_code=404, detail="Runbook step not found")
    return step

@router.post("/", response_model=RunbookStepInDB)
def create(data: RunbookStepCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    step = RunbookStepRepository(db, redis).create(data.dict())
    index_runbook_step(step)
    return step

@router.put("/{step_id}", response_model=RunbookStepInDB)
def update(step_id: UUID, data: RunbookStepUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    step = RunbookStepRepository(db, redis).update(step_id, data.dict(exclude_unset=True))
    if not step:
        raise HTTPException(status_code=404, detail="Runbook step not found")
    db.refresh(step)
    index_runbook_step(step)
    return step

@router.delete("/soft/{step_id}", response_model=RunbookStepInDB)
def soft_delete(step_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    step = RunbookStepRepository(db, redis).soft_delete(step_id)
    if not step:
        raise HTTPException(status_code=404, detail="Runbook step not found")
    return step

@router.put("/restore/{step_id}", response_model=RunbookStepInDB)
def restore(step_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    step = RunbookStepRepository(db, redis).restore(step_id)
    if not step:
        raise HTTPException(status_code=404, detail="Runbook step not found")
    return step

@router.delete("/hard/{step_id}", response_model=RunbookStepInDB)
def hard_delete(step_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    step = RunbookStepRepository(db, redis).hard_delete(step_id)
    if not step:
        raise HTTPException(status_code=404, detail="Runbook step not found")
    return step

@router.get("/search/{keyword}", response_model=list[RunbookStepInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return RunbookStepRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    steps = db.query(RunbookStep).filter_by(is_deleted=False).all()
    for step in steps:
        index_runbook_step(step)
    return {"message": f"{len(steps)} runbook steps indexed to Elasticsearch"}
