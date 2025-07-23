from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

INDEX_NAME = "endpoint_types"
es = get_elasticsearch_connection()

def serialize_endpoint_type(endpoint_type):
    return {
        "endpoint_type_id": str(endpoint_type.endpoint_type_id),
        "name": endpoint_type.name,
        "category": endpoint_type.category,
        "description": endpoint_type.description or "",
        "created_at": endpoint_type.created_at.isoformat() if endpoint_type.created_at else None,
        "updated_at": endpoint_type.updated_at.isoformat() if endpoint_type.updated_at else None,
        "deleted_at": endpoint_type.deleted_at.isoformat() if endpoint_type.deleted_at else None,
    }

def index_endpoint_type(endpoint_type):
    try:
        doc = serialize_endpoint_type(endpoint_type)
        es.index(index=INDEX_NAME, id=str(endpoint_type.endpoint_type_id), body=doc, refresh=True)
        print(f"✅ EndpointType {endpoint_type.endpoint_type_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing EndpointType {endpoint_type.endpoint_type_id}: {e}")

def get_endpoint_type_from_es(endpoint_type_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(endpoint_type_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get EndpointType error: {str(e)}")
        return None

def get_all_endpoint_types_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search EndpointTypes error: {str(e)}")
        return []
