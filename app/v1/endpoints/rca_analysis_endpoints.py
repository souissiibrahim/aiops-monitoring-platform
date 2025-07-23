from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.rca_analysis import RCAAnalysisCreate, RCAAnalysisRead
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.db.repositories.rca_analysis_repository import RCAAnalysisRepository
from app.db.models.rca_analysis import RCAAnalysis
from app.services.elasticsearch.rca_analysis_service import index_rca
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    rcas = RCAAnalysisRepository(db, redis).get_all()
    return success_response(serialize(rcas, RCAAnalysisRead), "RCA records fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    rcas = RCAAnalysisRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(rcas, RCAAnalysisRead), "Deleted RCA records fetched successfully.")


@router.get("/{rca_id}")
def get_by_id(rca_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    rca = RCAAnalysisRepository(db, redis).get_by_id(rca_id)
    if not rca:
        return error_response("RCA not found", 404)
    return success_response(serialize(rca, RCAAnalysisRead), "RCA record fetched successfully.")


@router.post("/")
def create(data: RCAAnalysisCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    rca = RCAAnalysisRepository(db, redis).create(data.dict())
    index_rca(rca)
    return success_response(serialize(rca, RCAAnalysisRead), "RCA record created successfully.", 201)


@router.put("/{rca_id}")
def update(rca_id: UUID, data: RCAAnalysisCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RCAAnalysisRepository(db, redis).update(rca_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("RCA not found", 404)
    index_rca(result)
    return success_response(serialize(result, RCAAnalysisRead), "RCA record updated successfully.")


@router.delete("/soft/{rca_id}")
def soft_delete(rca_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RCAAnalysisRepository(db, redis).soft_delete(rca_id)
    if not result:
        return error_response("RCA not found", 404)
    return success_response(serialize(result, RCAAnalysisRead), "RCA record soft deleted successfully.")


@router.put("/restore/{rca_id}")
def restore(rca_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RCAAnalysisRepository(db, redis).restore(rca_id)
    if not result:
        return error_response("RCA not found", 404)
    return success_response(serialize(result, RCAAnalysisRead), "RCA record restored successfully.")


@router.delete("/hard/{rca_id}")
def hard_delete(rca_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = RCAAnalysisRepository(db, redis).hard_delete(rca_id)
    if not result:
        return error_response("RCA not found", 404)
    return success_response(serialize(result, RCAAnalysisRead), "RCA record permanently deleted.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = RCAAnalysisRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, RCAAnalysisRead), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    rcas = db.query(RCAAnalysis).filter_by(is_deleted=False).all()
    for rca in rcas:
        index_rca(rca)
    return success_response({"count": len(rcas)}, "All RCA records indexed to Elasticsearch.")
