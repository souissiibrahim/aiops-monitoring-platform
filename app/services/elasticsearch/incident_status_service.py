from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "incident_statuses"

def serialize_incident_status(status):
    return {
        "status_id": str(status.status_id),
        "name": status.name,
        "description": status.description or "",
        "created_at": status.created_at.isoformat() if status.created_at else None,
        "updated_at": status.updated_at.isoformat() if status.updated_at else None,
        "deleted_at": status.deleted_at.isoformat() if status.deleted_at else None,
    }

def index_incident_status(status):
    try:
        doc = serialize_incident_status(status)
        es.index(index=INDEX_NAME, id=str(status.status_id), body=doc, refresh=True)
        print(f"✅ IncidentStatus {status.status_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing incident status {status.status_id}: {e}")

def get_incident_status_from_es(status_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(status_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get incident status error: {str(e)}")
        return None

def get_all_incident_statuses_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search incident statuses error: {str(e)}")
        return []
