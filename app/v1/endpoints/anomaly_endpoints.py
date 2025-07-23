from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.anomaly import AnomalyCreate, AnomalyUpdate, AnomalyInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.anomaly_repository import AnomalyRepository
from app.db.models.anomaly import Anomaly
from app.services.elasticsearch.anomaly_service import index_anomaly

router = APIRouter()

@router.get("/", response_model=list[AnomalyInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return AnomalyRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[AnomalyInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return AnomalyRepository(db, redis).get_all_soft_deleted()

@router.get("/{anomaly_id}", response_model=AnomalyInDB)
def get_by_id(anomaly_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    anomaly = AnomalyRepository(db, redis).get_by_id(anomaly_id)
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return anomaly

@router.post("/", response_model=AnomalyInDB)
def create(data: AnomalyCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    anomaly = AnomalyRepository(db, redis).create(data.dict())
    index_anomaly(anomaly)
    return anomaly

@router.put("/{anomaly_id}", response_model=AnomalyInDB)
def update(anomaly_id: UUID, data: AnomalyUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AnomalyRepository(db, redis).update(anomaly_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    db.refresh(result)
    index_anomaly(result)
    return result

@router.delete("/soft/{anomaly_id}", response_model=AnomalyInDB)
def soft_delete(anomaly_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AnomalyRepository(db, redis).soft_delete(anomaly_id)
    if not result:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return result

@router.put("/restore/{anomaly_id}", response_model=AnomalyInDB)
def restore(anomaly_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AnomalyRepository(db, redis).restore(anomaly_id)
    if not result:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return result

@router.delete("/hard/{anomaly_id}", response_model=AnomalyInDB)
def hard_delete(anomaly_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AnomalyRepository(db, redis).hard_delete(anomaly_id)
    if not result:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return result

@router.get("/search/{keyword}", response_model=list[AnomalyInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return AnomalyRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    anomalies = db.query(Anomaly).filter_by(is_deleted=False).all()
    for anomaly in anomalies:
        index_anomaly(anomaly)
    return {"message": f"{len(anomalies)} anomalies indexed to Elasticsearch"}
