from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "runbook_steps"

def serialize_runbook_step(step):
    return {
        "step_id": str(step.step_id),
        "runbook_id": str(step.runbook_id),
        "step_number": step.step_number,
        "action_type": step.action_type or "",
        "description": step.description or "",
        "command_or_script": step.command_or_script or "",
        "timeout_minutes": step.timeout_minutes,
        "success_condition": step.success_condition or "",
        "created_at": step.created_at.isoformat() if step.created_at else None,
        "updated_at": step.updated_at.isoformat() if step.updated_at else None,
        "deleted_at": step.deleted_at.isoformat() if step.deleted_at else None,
    }

def index_runbook_step(step):
    try:
        doc = serialize_runbook_step(step)
        es.index(index=INDEX_NAME, id=str(step.step_id), body=doc, refresh=True)
        print(f"✅ Runbook step {step.step_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing runbook step {step.step_id}: {e}")

def get_runbook_step_from_es(step_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(step_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get runbook step error: {str(e)}")
        return None

def get_all_runbook_steps_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search runbook steps error: {str(e)}")
        return []
