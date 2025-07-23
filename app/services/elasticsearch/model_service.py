from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "models"

def serialize_model(model):
    return {
        "model_id": str(model.model_id),
        "name": model.name,
        "type": model.type,
        "version": model.version,
        "accuracy": model.accuracy,
        "created_at": model.created_at.isoformat() if model.created_at else None,
        "updated_at": model.updated_at.isoformat() if model.updated_at else None,
        "deleted_at": model.deleted_at.isoformat() if model.deleted_at else None,
    }

def index_model(model):
    try:
        doc = serialize_model(model)
        es.index(index=INDEX_NAME, id=str(model.model_id), body=doc, refresh=True)
        print(f"✅ Model {model.model_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing model {model.model_id}: {e}")
