from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from datetime import datetime
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "incidents"

def serialize_incident(incident):
    return {
        "incident_id": str(incident.incident_id),
        "service_id": str(incident.service_id),
        "source_id": str(incident.source_id),
        "incident_type_id": str(incident.incident_type_id),
        "severity_level_id": str(incident.severity_level_id),
        "status_id": str(incident.status_id),
        "root_cause_id": str(incident.root_cause_id) if incident.root_cause_id else None,
        "start_timestamp": incident.start_timestamp.isoformat(),
        "end_timestamp": incident.end_timestamp.isoformat() if incident.end_timestamp else None,
        "description": incident.description or "",
        "escalation_level": incident.escalation_level,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "updated_at": incident.updated_at.isoformat() if incident.updated_at else None,
        "deleted_at": incident.deleted_at.isoformat() if incident.deleted_at else None,
    }

def index_incident(incident):
    try:
        doc = serialize_incident(incident)
        es.index(index=INDEX_NAME, id=str(incident.incident_id), body=doc, refresh=True)
        print(f"✅ Incident {incident.incident_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing incident {incident.incident_id}: {e}")

def get_incident_from_es(incident_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(incident_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get incident error: {str(e)}")
        return None

def get_all_incidents_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search incidents error: {str(e)}")
        return []
