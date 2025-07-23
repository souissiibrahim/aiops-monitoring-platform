from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "predictions"

def serialize_prediction(prediction):
    return {
        "prediction_id": str(prediction.prediction_id),
        "model_id": str(prediction.model_id) if prediction.model_id else None,
        "input_features": prediction.input_features,
        "prediction_output": prediction.prediction_output,
        "confidence_score": prediction.confidence_score,
        "prediction_timestamp": prediction.prediction_timestamp.isoformat() if prediction.prediction_timestamp else None,
        "incident_id": str(prediction.incident_id) if prediction.incident_id else None,
        "status": prediction.status,
        "explanation_id": str(prediction.explanation_id) if prediction.explanation_id else None,
        "created_at": prediction.created_at.isoformat() if prediction.created_at else None,
        "updated_at": prediction.updated_at.isoformat() if prediction.updated_at else None,
        "deleted_at": prediction.deleted_at.isoformat() if prediction.deleted_at else None,
    }

def index_prediction(prediction):
    try:
        doc = serialize_prediction(prediction)
        es.index(index=INDEX_NAME, id=str(prediction.prediction_id), body=doc, refresh=True)
        print(f"✅ Prediction {prediction.prediction_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing prediction {prediction.prediction_id}: {e}")
