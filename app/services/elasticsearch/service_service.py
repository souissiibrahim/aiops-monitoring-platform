from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "services"

def serialize_service(service):
    return {
        "service_id": str(service.service_id),
        "name": service.name,
        "description": service.description or "",
        "criticality_level": service.criticality_level or "Medium",
        "owner_team_id": str(service.owner_team_id) if service.owner_team_id else None,
        "created_at": service.created_at.isoformat() if service.created_at else None,
        "updated_at": service.updated_at.isoformat() if service.updated_at else None,
        "deleted_at": service.deleted_at.isoformat() if service.deleted_at else None,
    }

def index_service(service):
    try:
        doc = serialize_service(service)
        es.index(index=INDEX_NAME, id=str(service.service_id), body=doc, refresh=True)
        print(f"✅ Service {service.service_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing service {service.service_id}: {e}")

def get_service_from_es(service_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(service_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get service error: {str(e)}")
        return None

def get_all_services_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search services error: {str(e)}")
        return []
