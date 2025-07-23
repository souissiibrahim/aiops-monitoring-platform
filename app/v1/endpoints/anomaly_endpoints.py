from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.anomaly import AnomalyCreate, AnomalyUpdate, AnomalyInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.anomaly_repository import AnomalyRepository
from app.db.models.anomaly import Anomaly
from app.services.elasticsearch.anomaly_service import index_anomaly
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    anomalies = AnomalyRepository(db, redis).get_all()
    return success_response(serialize(anomalies, AnomalyInDB), "Anomalies fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    anomalies = AnomalyRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(anomalies, AnomalyInDB), "Soft deleted anomalies fetched successfully.")


@router.get("/{anomaly_id}")
def get_by_id(anomaly_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    anomaly = AnomalyRepository(db, redis).get_by_id(anomaly_id)
    if not anomaly:
        return error_response("Anomaly not found", 404)
    return success_response(serialize(anomaly, AnomalyInDB), "Anomaly fetched successfully.")


@router.post("/")
def create(data: AnomalyCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    anomaly = AnomalyRepository(db, redis).create(data.dict())
    try:
        index_anomaly(anomaly)
    except Exception as e:
        print(f"❌ Failed to index anomaly after creation: {e}")
    return success_response(serialize(anomaly, AnomalyInDB), "Anomaly created successfully.", 201)


@router.put("/{anomaly_id}")
def update(anomaly_id: UUID, data: AnomalyUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AnomalyRepository(db, redis).update(anomaly_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Anomaly not found", 404)
    try:
        db.refresh(result)
        index_anomaly(result)
    except Exception as e:
        print(f"❌ Failed to reindex anomaly after update: {e}")
    return success_response(serialize(result, AnomalyInDB), "Anomaly updated successfully.")


@router.delete("/soft/{anomaly_id}")
def soft_delete(anomaly_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AnomalyRepository(db, redis).soft_delete(anomaly_id)
    if not result:
        return error_response("Anomaly not found", 404)
    return success_response(serialize(result, AnomalyInDB), "Anomaly soft deleted successfully.")


@router.put("/restore/{anomaly_id}")
def restore(anomaly_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AnomalyRepository(db, redis).restore(anomaly_id)
    if not result:
        return error_response("Anomaly not found", 404)
    return success_response(serialize(result, AnomalyInDB), "Anomaly restored successfully.")


@router.delete("/hard/{anomaly_id}")
def hard_delete(anomaly_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = AnomalyRepository(db, redis).hard_delete(anomaly_id)
    if not result:
        return error_response("Anomaly not found", 404)
    return success_response(serialize(result, AnomalyInDB), "Anomaly permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = AnomalyRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, AnomalyInDB), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    anomalies = db.query(Anomaly).filter_by(is_deleted=False).all()
    count = 0
    for anomaly in anomalies:
        try:
            index_anomaly(anomaly)
            count += 1
        except Exception as e:
            print(f"❌ Failed to index anomaly {anomaly.id}: {e}")
    return success_response({"count": count}, "All anomalies indexed to Elasticsearch.")
