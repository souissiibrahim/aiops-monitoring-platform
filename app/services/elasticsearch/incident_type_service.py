from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "incident_types"

def serialize_incident_type(incident_type):
    return {
        "incident_type_id": str(incident_type.incident_type_id),
        "name": incident_type.name,
        "description": incident_type.description or "",
        "category": incident_type.category or "",
        "created_at": incident_type.created_at.isoformat() if incident_type.created_at else None,
        "updated_at": incident_type.updated_at.isoformat() if incident_type.updated_at else None,
        "deleted_at": incident_type.deleted_at.isoformat() if incident_type.deleted_at else None,
    }

def index_incident_type(incident_type):
    try:
        doc = serialize_incident_type(incident_type)
        es.index(index=INDEX_NAME, id=str(incident_type.incident_type_id), body=doc, refresh=True)
        print(f"✅ IncidentType {incident_type.incident_type_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing IncidentType {incident_type.incident_type_id}: {e}")

def get_incident_type_from_es(incident_type_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(incident_type_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get IncidentType error: {str(e)}")
        return None

def get_all_incident_types_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search IncidentTypes error: {str(e)}")
        return []
