from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "service_endpoints"

def serialize_service_endpoint(endpoint):
    return {
        "service_endpoint_id": str(endpoint.service_endpoint_id),
        "service_id": str(endpoint.service_id),
        "source_id": str(endpoint.source_id),
        "role_in_service": endpoint.role_in_service or "",
        "created_at": endpoint.created_at.isoformat() if endpoint.created_at else None,
        "updated_at": endpoint.updated_at.isoformat() if endpoint.updated_at else None,
        "deleted_at": endpoint.deleted_at.isoformat() if endpoint.deleted_at else None,
    }

def index_service_endpoint(endpoint):
    try:
        doc = serialize_service_endpoint(endpoint)
        es.index(index=INDEX_NAME, id=str(endpoint.service_endpoint_id), body=doc, refresh=True)
        print(f"✅ Service endpoint {endpoint.service_endpoint_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing service endpoint {endpoint.service_endpoint_id}: {e}")

def get_service_endpoint_from_es(endpoint_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(endpoint_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get service endpoint error: {str(e)}")
        return None

def get_all_service_endpoints_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search service endpoints error: {str(e)}")
        return []
