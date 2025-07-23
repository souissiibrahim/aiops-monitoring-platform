from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from datetime import datetime
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "telemetry_sources"

def serialize_telemetry_source(source):
    return {
        "source_id": str(source.source_id),
        "name": source.name,
        "endpoint_type_id": str(source.endpoint_type_id),
        "environment_id": str(source.environment_id),
        "location_id": str(source.location_id),
        "metadata_info": source.metadata_info or {},
        "created_at": source.created_at.isoformat() if source.created_at else None,
        "updated_at": source.updated_at.isoformat() if source.updated_at else None,
        "deleted_at": source.deleted_at.isoformat() if source.deleted_at else None,
    }

def index_telemetry_source(source):
    try:
        doc = serialize_telemetry_source(source)
        es.index(index=INDEX_NAME, id=str(source.source_id), body=doc, refresh=True)
        print(f"✅ Telemetry Source {source.source_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing telemetry source {source.source_id}: {e}")

def get_telemetry_source_from_es(source_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(source_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get telemetry source error: {str(e)}")
        return None

def get_all_telemetry_sources_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search telemetry sources error: {str(e)}")
        return []
