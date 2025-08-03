from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from typing import List

from app.v1.schemas.rca_analysis import RCAAnalysisCreate, RCAAnalysisRead
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.db.models.rca_analysis import RCAAnalysis
from app.db.models.incident import Incident
from app.services.elasticsearch.rca_analysis_service import index_rca
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.utils.response import success_response, error_response
from sqlalchemy import or_
import os

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


@router.get("/rca-stats/dashboard")
def get_rca_dashboard_metrics(db: Session = Depends(get_db)):
   
    active = db.query(Incident)\
        .filter(Incident.root_cause_id != None)\
        .filter(Incident.status.has(Incident.status.property.mapper.class_.name.ilike("%open%")))\
        .count()

    
    completed_incidents = db.query(Incident)\
        .filter(Incident.root_cause_id != None)\
        .filter(Incident.end_timestamp != None)\
        .filter(
            or_(
                Incident.status.has(Incident.status.property.mapper.class_.name.ilike("%resolved%")),
                Incident.status.has(Incident.status.property.mapper.class_.name.ilike("%closed%"))
            )
        ).all()

    
    avg_resolution = 0.0
    if completed_incidents:
        total_secs = sum(
            (i.end_timestamp - i.start_timestamp).total_seconds()
            for i in completed_incidents
            if i.start_timestamp and i.end_timestamp
        )
        if total_secs > 0:
            avg_resolution = round((total_secs / len(completed_incidents)) / 3600, 1)

    
    kb_count = 0
    kb_path = "faiss_index/known_logs.jsonl"
    if os.path.exists(kb_path):
        with open(kb_path, "r") as f:
            kb_count = sum(1 for _ in f)

    return success_response({
        "active": active or 0,
        "completed": len(completed_incidents) or 0,
        "avg_resolution_hours": avg_resolution or 0,
        "kb_count": kb_count or 0
    }, "Dashboard RCA stats loaded.")


@router.get("/dashboard-summaries")
def get_dashboard_summaries(db: Session = Depends(get_db)):
    rcas = db.query(RCAAnalysis)\
        .options(joinedload(RCAAnalysis.incident), joinedload(RCAAnalysis.team))\
        .filter(RCAAnalysis.is_deleted == False)\
        .order_by(RCAAnalysis.analysis_timestamp.desc())\
        .all()

    summaries = []

    for rca in rcas:
        incident = rca.incident
        team_name = rca.team.name if rca.team else "AI Agent"

        title = incident.title if incident else "Unknown"
        incident_id = str(incident.incident_id) if incident else "Unknown"
        started = incident.start_timestamp.isoformat() if incident and incident.start_timestamp else "Unknown"
        status = incident.status.name if incident and incident.status else "Unknown"
        severity = incident.severity_level.name if incident and incident.severity_level else "Unknown"
        root_cause = incident.description if incident and incident.description else "N/A"

        if incident and incident.end_timestamp and incident.start_timestamp:
            duration = str(incident.end_timestamp - incident.start_timestamp)
        else:
            duration = "Ongoing"

        tags = []
        if status != "Unknown":
            tags.append(status)
        if severity != "Unknown":
            tags.append(severity)
        tags.append(rca.analysis_method or "Unknown")

        summaries.append({
            "rca_id": str(rca.rca_id),
            "title": title,
            "incident_id": incident_id,
            "investigator": team_name,
            "started": started,
            "duration": duration,
            "status": status,
            "severity": severity,
            "root_cause": root_cause,
            "recommendations": rca.recommendations or [],
            "tags": tags
        })

    return success_response(summaries, "Dashboard RCA summaries loaded.")

@router.get("/rca-analysis/knowledge-base", response_model=List[dict])
def get_knowledge_base_cards(db: Session = Depends(get_db)):
    rca_entries = db.query(RCAAnalysis).options(
        joinedload(RCAAnalysis.incident).joinedload(Incident.incident_type)
    ).filter(RCAAnalysis.is_deleted == False).order_by(RCAAnalysis.created_at.desc()).all()

    result = []
    for rca in rca_entries:
        if not isinstance(rca.recommendations, list) or not rca.recommendations:
            continue

        top_reco = max(rca.recommendations, key=lambda r: r.get("confidence", 0.0))

        result.append({
            "title": rca.incident.description if rca.incident and rca.incident.description else "Unknown root cause",
            "description": top_reco.get("text", "No recommendation"),
            "category": (
                rca.incident.incident_type.name
                if rca.incident and rca.incident.incident_type
                else "Unknown"
            ),
            "last_updated": (rca.updated_at or rca.created_at).isoformat(),
            "relevance": round(top_reco.get("confidence", 0.0), 2)
        })

    return result



@router.get("/timeline-analysis")
def get_timeline_events(db: Session = Depends(get_db)):
    incidents = db.query(Incident)\
        .options(
            joinedload(Incident.source),
            joinedload(Incident.severity_level)
        )\
        .filter(Incident.root_cause_id != None)\
        .order_by(Incident.start_timestamp.asc())\
        .all()

    timeline_events = []
    for i in incidents:
        timeline_events.append({
            "title": i.title or "No title",
            "source": i.source.name if i.source else "Unknown",
            "impact": i.severity_level.name if i.severity_level else "Unknown",
            "timestamp": i.start_timestamp.isoformat() if i.start_timestamp else "Unknown"
        })

    return success_response(timeline_events, "Timeline analysis loaded.")

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
