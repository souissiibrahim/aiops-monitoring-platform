from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from datetime import datetime

es = get_elasticsearch_connection()
INDEX_NAME = "log_entries"

def index_log_entry(log_entry):
    try:
        doc = {
            "id": log_entry.id,
            "incident_id": log_entry.incident_id,
            "service": log_entry.service or "",
            "level": log_entry.level or "",
            "message": log_entry.message or "",
            "timestamp": log_entry.timestamp.isoformat() if log_entry.timestamp else datetime.utcnow().isoformat(),
            "created_at": log_entry.created_at.isoformat() if log_entry.created_at else datetime.utcnow().isoformat(),
            "updated_at": log_entry.updated_at.isoformat() if log_entry.updated_at else datetime.utcnow().isoformat(),
            "deleted_at": log_entry.deleted_at.isoformat() if log_entry.deleted_at else None
        }

        print(f"📦 Indexing document to ES: {doc}")

        es.index(index=INDEX_NAME, id=log_entry.id, body=doc, refresh=True)
        print(f"✅ LogEntry {log_entry.id} indexed to Elasticsearch.")
    except Exception as e:
        print(f"❌ Error indexing LogEntry {log_entry.id}: {e}")

def get_log_entry_from_es(entry_id):
    try:
        result = es.get(index=INDEX_NAME, id=entry_id)
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"❌ Error fetching LogEntry {entry_id}: {e}")
        return None

def get_all_log_entries_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"❌ Error fetching log entries: {e}")
        return []
