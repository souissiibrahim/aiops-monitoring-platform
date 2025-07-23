from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.v1.schemas.rca_report_schemas import RCAReportCreate, RCAReportUpdate, RCAReportOut
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.rca_report_repository import RCAReportRepository
from app.db.models.rca_report import RCAReport
from app.services.elasticsearch.rca_report_service import index_rca_report

#router = APIRouter(prefix="/rca-reports", tags=["RCA Reports"])
router = APIRouter()

@router.get("/", response_model=list[RCAReportOut])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return RCAReportRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[RCAReportOut])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return RCAReportRepository(db, redis).get_all_soft_deleted()

@router.get("/{report_id}", response_model=RCAReportOut)
def get_by_id(report_id: int, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    report = RCAReportRepository(db, redis).get_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="RCA Report not found")
    return report

@router.post("/", response_model=RCAReportOut)
def create(data: RCAReportCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    report = RCAReportRepository(db, redis).create(data.dict())
    index_rca_report(report)
    return report

@router.put("/{report_id}", response_model=RCAReportOut)
def update(report_id: int, data: RCAReportUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RCAReportRepository(db, redis).update(report_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="RCA Report not found")

    db.refresh(result)
    index_rca_report(result)
    return result

@router.delete("/soft/{report_id}", response_model=RCAReportOut)
def soft_delete(report_id: int, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RCAReportRepository(db, redis).soft_delete(report_id)
    if not result:
        raise HTTPException(status_code=404, detail="RCA Report not found")
    return result

@router.put("/restore/{report_id}", response_model=RCAReportOut)
def restore(report_id: int, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RCAReportRepository(db, redis).restore(report_id)
    if not result:
        raise HTTPException(status_code=404, detail="RCA Report not found")
    return result

@router.delete("/hard/{report_id}", response_model=RCAReportOut)
def hard_delete(report_id: int, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RCAReportRepository(db, redis).hard_delete(report_id)
    if not result:
        raise HTTPException(status_code=404, detail="RCA Report not found")
    return result

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    reports = db.query(RCAReport).filter_by(is_deleted=False).all()
    for report in reports:
        index_rca_report(report)
    return {"message": f"{len(reports)} RCA reports indexed to Elasticsearch"}

@router.get("/search/{keyword}", response_model=list[RCAReportOut])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return RCAReportRepository(db, redis).search(keyword, es)