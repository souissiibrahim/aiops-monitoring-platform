from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from uuid import UUID

from app.v1.schemas.rca_analysis import RCAAnalysisCreate, RCAAnalysisRead
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.db.models.rca_analysis import RCAAnalysis
from app.db.models.incident import Incident
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
    rcas = db.query(RCAAnalysis) \
        .options(joinedload(RCAAnalysis.incident), joinedload(RCAAnalysis.team)) \
        .filter(RCAAnalysis.is_deleted == False).all()
    return success_response(serialize(rcas, RCAAnalysisRead), "RCA records fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    rcas = db.query(RCAAnalysis) \
        .options(joinedload(RCAAnalysis.incident), joinedload(RCAAnalysis.team)) \
        .filter(RCAAnalysis.is_deleted == True).all()
    return success_response(serialize(rcas, RCAAnalysisRead), "Deleted RCA records fetched successfully.")


@router.get("/{rca_id}")
def get_by_id(rca_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    rca = db.query(RCAAnalysis) \
        .options(joinedload(RCAAnalysis.incident), joinedload(RCAAnalysis.team)) \
        .filter_by(rca_id=rca_id).first()
    if not rca:
        return error_response("RCA not found", 404)
    return success_response(serialize(rca, RCAAnalysisRead), "RCA record fetched successfully.")


@router.post("/")
def create(data: RCAAnalysisCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    rca = RCAAnalysis(**data.dict())
    db.add(rca)
    db.commit()
    db.refresh(rca)

    # Link RCA to Incident by setting root_cause_id
    incident = db.query(Incident).filter(Incident.incident_id == rca.incident_id).first()
    if incident:
        incident.root_cause_id = rca.rca_id
        db.commit()

    # Reload with relationships
    rca = db.query(RCAAnalysis) \
        .options(joinedload(RCAAnalysis.incident), joinedload(RCAAnalysis.team)) \
        .filter_by(rca_id=rca.rca_id).first()

    index_rca(rca)
    return success_response(serialize(rca, RCAAnalysisRead), "RCA record created successfully.", 201)


@router.put("/{rca_id}")
def update(rca_id: UUID, data: RCAAnalysisCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    rca = db.query(RCAAnalysis).filter_by(rca_id=rca_id).first()
    if not rca:
        return error_response("RCA not found", 404)

    for key, value in data.dict(exclude_unset=True).items():
        setattr(rca, key, value)

    db.commit()
    db.refresh(rca)

    # Link RCA to Incident by setting root_cause_id
    incident = db.query(Incident).filter(Incident.incident_id == rca.incident_id).first()
    if incident:
        incident.root_cause_id = rca.rca_id
        db.commit()

    rca = db.query(RCAAnalysis) \
        .options(joinedload(RCAAnalysis.incident), joinedload(RCAAnalysis.team)) \
        .filter_by(rca_id=rca_id).first()

    index_rca(rca)
    return success_response(serialize(rca, RCAAnalysisRead), "RCA record updated successfully.")


@router.delete("/soft/{rca_id}")
def soft_delete(rca_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    rca = db.query(RCAAnalysis).filter_by(rca_id=rca_id).first()
    if not rca:
        return error_response("RCA not found", 404)
    rca.is_deleted = True
    db.commit()
    return success_response(serialize(rca, RCAAnalysisRead), "RCA record soft deleted successfully.")


@router.put("/restore/{rca_id}")
def restore(rca_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    rca = db.query(RCAAnalysis).filter_by(rca_id=rca_id).first()
    if not rca:
        return error_response("RCA not found", 404)
    rca.is_deleted = False
    db.commit()
    return success_response(serialize(rca, RCAAnalysisRead), "RCA record restored successfully.")


@router.delete("/hard/{rca_id}")
def hard_delete(rca_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    rca = db.query(RCAAnalysis).filter_by(rca_id=rca_id).first()
    if not rca:
        return error_response("RCA not found", 404)
    db.delete(rca)
    db.commit()
    return success_response({}, "RCA record permanently deleted.")


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
