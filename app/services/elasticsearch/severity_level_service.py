from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "severity_levels"

def serialize_severity_level(severity_level):
    return {
        "severity_level_id": str(severity_level.severity_level_id),
        "name": severity_level.name,
        "impact_score": severity_level.impact_score,
        "description": severity_level.description or "",
        "sla_hours": severity_level.sla_hours,
        "is_deleted": severity_level.is_deleted,
        "created_at": severity_level.created_at.isoformat() if severity_level.created_at else None,
        "updated_at": severity_level.updated_at.isoformat() if severity_level.updated_at else None,
        "deleted_at": severity_level.deleted_at.isoformat() if severity_level.deleted_at else None,
    }

def index_severity_level(severity_level):
    try:
        doc = serialize_severity_level(severity_level)
        es.index(index=INDEX_NAME, id=str(severity_level.severity_level_id), body=doc, refresh=True)
        print(f"✅ SeverityLevel {severity_level.severity_level_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing severity level {severity_level.severity_level_id}: {e}")

def get_severity_level_from_es(severity_level_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(severity_level_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get severity level error: {str(e)}")
        return None

def get_all_severity_levels_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search severity levels error: {str(e)}")
        return []
