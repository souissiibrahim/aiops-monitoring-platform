from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "environments"

def serialize_environment(env):
    return {
        "environment_id": str(env.environment_id),
        "name": env.name,
        "description": env.description or "",
        "created_at": env.created_at.isoformat() if env.created_at else None,
        "updated_at": env.updated_at.isoformat() if env.updated_at else None,
        "is_deleted": env.is_deleted,
        "deleted_at": env.deleted_at.isoformat() if env.deleted_at else None,
    }

def index_environment(env):
    try:
        doc = serialize_environment(env)
        es.index(index=INDEX_NAME, id=str(env.environment_id), body=doc, refresh=True)
        print(f"✅ Environment {env.environment_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing environment {env.environment_id}: {e}")

def get_environment_from_es(environment_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(environment_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get environment error: {str(e)}")
        return None

def get_all_environments_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search environments error: {str(e)}")
        return []
