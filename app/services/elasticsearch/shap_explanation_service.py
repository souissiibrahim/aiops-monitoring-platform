from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID
from datetime import datetime
from app.db.models.shap_explanation import ShapExplanation

es = get_elasticsearch_connection()
INDEX_NAME = "shap_explanations"

def serialize_shap_explanation(explanation: ShapExplanation):
    return {
        "explanation_id": str(explanation.explanation_id),
        "explanation_text": explanation.explanation_text or "",
        "created_at": explanation.created_at.isoformat() if explanation.created_at else None,
        "updated_at": explanation.updated_at.isoformat() if explanation.updated_at else None,
        "is_deleted": explanation.is_deleted,
        "deleted_at": explanation.deleted_at.isoformat() if explanation.deleted_at else None,
    }

def index_shap_explanation(explanation: ShapExplanation):
    try:
        doc = serialize_shap_explanation(explanation)
        es.index(index=INDEX_NAME, id=str(explanation.explanation_id), body=doc, refresh=True)
        print(f"✅ SHAP Explanation {explanation.explanation_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing SHAP Explanation {explanation.explanation_id}: {e}")

def get_shap_explanation_from_es(explanation_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(explanation_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get SHAP Explanation error: {str(e)}")
        return None

def get_all_shap_explanations_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search SHAP Explanations error: {str(e)}")
        return []
