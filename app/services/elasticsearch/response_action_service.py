from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "response_actions"

def serialize_response_action(action):
    return {
        "action_id": str(action.action_id),
        "incident_id": str(action.incident_id),
        "runbook_id": str(action.runbook_id),
        "step_id": str(action.step_id),
        "executed_by_team_id": str(action.executed_by_team_id) if action.executed_by_team_id else None,
        "status": action.status,
        "execution_log": action.execution_log or "",
        "started_at": action.started_at.isoformat() if action.started_at else None,
        "completed_at": action.completed_at.isoformat() if action.completed_at else None,
        "error_message": action.error_message or "",
        "created_at": action.created_at.isoformat() if action.created_at else None,
        "updated_at": action.updated_at.isoformat() if action.updated_at else None,
        "deleted_at": action.deleted_at.isoformat() if action.deleted_at else None,
    }

def index_response_action(action):
    try:
        doc = serialize_response_action(action)
        es.index(index=INDEX_NAME, id=str(action.action_id), body=doc, refresh=True)
        print(f"✅ ResponseAction {action.action_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing response action {action.action_id}: {e}")

def get_response_action_from_es(action_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(action_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get response action error: {str(e)}")
        return None

def get_all_response_actions_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search response actions error: {str(e)}")
        return []
