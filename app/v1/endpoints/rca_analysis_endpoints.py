from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.rca_analysis import RCAAnalysisCreate, RCAAnalysisRead
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.db.repositories.rca_analysis_repository import RCAAnalysisRepository
from app.db.models.rca_analysis import RCAAnalysis
from app.services.elasticsearch.rca_analysis_service import index_rca
from app.services.elasticsearch.connection import get_elasticsearch_connection


router = APIRouter()

@router.get("/", response_model=list[RCAAnalysisRead])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return RCAAnalysisRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[RCAAnalysisRead])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return RCAAnalysisRepository(db, redis).get_all_soft_deleted()

@router.get("/{rca_id}", response_model=RCAAnalysisRead)
def get_by_id(rca_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    rca = RCAAnalysisRepository(db, redis).get_by_id(rca_id)
    if not rca:
        raise HTTPException(status_code=404, detail="RCA not found")
    return rca

@router.post("/", response_model=RCAAnalysisRead)
def create(data: RCAAnalysisCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return RCAAnalysisRepository(db, redis).create(data.dict())

@router.put("/{rca_id}", response_model=RCAAnalysisRead)
def update(rca_id: UUID, data: RCAAnalysisCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RCAAnalysisRepository(db, redis).update(rca_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="RCA not found")
    return result

@router.delete("/soft/{rca_id}", response_model=RCAAnalysisRead)
def soft_delete(rca_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RCAAnalysisRepository(db, redis).soft_delete(rca_id)
    if not result:
        raise HTTPException(status_code=404, detail="RCA not found")
    return result

@router.put("/restore/{rca_id}", response_model=RCAAnalysisRead)
def restore(rca_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RCAAnalysisRepository(db, redis).restore(rca_id)
    if not result:
        raise HTTPException(status_code=404, detail="RCA not found")
    return result

@router.delete("/hard/{rca_id}", response_model=RCAAnalysisRead)
def hard_delete(rca_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RCAAnalysisRepository(db, redis).hard_delete(rca_id)
    if not result:
        raise HTTPException(status_code=404, detail="RCA not found")
    return result

@router.get("/search/{keyword}", response_model=list[RCAAnalysisRead])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return RCAAnalysisRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    rcas = db.query(RCAAnalysis).filter_by(is_deleted=False).all()
    for rca in rcas:
        index_rca(rca)
    return {"message": f"{len(rcas)} RCA entries indexed to Elasticsearch"}