from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "audit_logs"

def serialize_audit_log(log):
    return {
        "log_id": str(log.log_id),
        "user_id": str(log.user_id) if log.user_id else None,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": str(log.entity_id) if log.entity_id else None,
        "old_value": log.old_value,
        "new_value": log.new_value,
        "incident_id": str(log.incident_id) if log.incident_id else None,
        "team_id": str(log.team_id) if log.team_id else None,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "created_at": log.created_at.isoformat() if log.created_at else None,
        "updated_at": log.updated_at.isoformat() if log.updated_at else None,
        "deleted_at": log.deleted_at.isoformat() if log.deleted_at else None,
    }

def index_audit_log(log):
    try:
        doc = serialize_audit_log(log)
        es.index(index=INDEX_NAME, id=str(log.log_id), body=doc, refresh=True)
        print(f"✅ AuditLog {log.log_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing audit log {log.log_id}: {e}")

def get_audit_log_from_es(log_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(log_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get audit log error: {str(e)}")
        return None

def get_all_audit_logs_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search audit logs error: {str(e)}")
        return []
