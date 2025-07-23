from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "dependency_graph"

def serialize_dependency(dependency):
    return {
        "dependency_id": str(dependency.dependency_id),
        "dependent_service_id": str(dependency.dependent_service_id),
        "dependency_service_id": str(dependency.dependency_service_id),
        "dependency_type": dependency.dependency_type or "",
        "weight": dependency.weight,
        "created_at": dependency.created_at.isoformat() if dependency.created_at else None,
        "updated_at": dependency.updated_at.isoformat() if dependency.updated_at else None,
        "deleted_at": dependency.deleted_at.isoformat() if dependency.deleted_at else None,
    }

def index_dependency_graph(dependency):
    try:
        doc = serialize_dependency(dependency)
        es.index(index=INDEX_NAME, id=str(dependency.dependency_id), body=doc, refresh=True)
        print(f"✅ Dependency {dependency.dependency_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing dependency {dependency.dependency_id}: {e}")

def get_dependency_from_es(dependency_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(dependency_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get dependency error: {str(e)}")
        return None

def get_all_dependencies_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search dependencies error: {str(e)}")
        return []
