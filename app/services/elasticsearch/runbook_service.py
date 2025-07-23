from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "runbooks"

def serialize_runbook(runbook):
    return {
        "runbook_id": str(runbook.runbook_id),
        "name": runbook.name,
        "description": runbook.description or "",
        "incident_type_id": str(runbook.incident_type_id) if runbook.incident_type_id else None,
        "service_id": str(runbook.service_id) if runbook.service_id else None,
        "team_id": str(runbook.team_id) if runbook.team_id else None,
        "priority": runbook.priority,
        "created_at": runbook.created_at.isoformat() if runbook.created_at else None,
        "updated_at": runbook.updated_at.isoformat() if runbook.updated_at else None,
        "deleted_at": runbook.deleted_at.isoformat() if runbook.deleted_at else None,
    }

def index_runbook(runbook):
    try:
        doc = serialize_runbook(runbook)
        es.index(index=INDEX_NAME, id=str(runbook.runbook_id), body=doc, refresh=True)
        print(f"✅ Runbook {runbook.runbook_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing runbook {runbook.runbook_id}: {e}")

def get_runbook_from_es(runbook_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(runbook_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get runbook error: {str(e)}")
        return None

def get_all_runbooks_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search runbooks error: {str(e)}")
        return []
