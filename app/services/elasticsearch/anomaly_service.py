from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "anomalies"

def serialize_anomaly(anomaly):
    return {
        "anomaly_id": str(anomaly.anomaly_id),
        "source_id": str(anomaly.source_id),
        "metric_type": anomaly.metric_type,
        "value": anomaly.value,
        "predicted_value": anomaly.predicted_value,
        "confidence_score": anomaly.confidence_score,
        "is_confirmed": anomaly.is_confirmed,
        "incident_id": str(anomaly.incident_id) if anomaly.incident_id else None,
        "detection_method": anomaly.detection_method,
        "timestamp": anomaly.timestamp.isoformat(),
        "anomaly_metadata": anomaly.anomaly_metadata,
        "created_at": anomaly.created_at.isoformat() if anomaly.created_at else None,
        "updated_at": anomaly.updated_at.isoformat() if anomaly.updated_at else None,
        "deleted_at": anomaly.deleted_at.isoformat() if anomaly.deleted_at else None,
    }

def index_anomaly(anomaly):
    try:
        doc = serialize_anomaly(anomaly)
        es.index(index=INDEX_NAME, id=str(anomaly.anomaly_id), body=doc, refresh=True)
        print(f"✅ Anomaly {anomaly.anomaly_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing anomaly {anomaly.anomaly_id}: {e}")

def get_anomaly_from_es(anomaly_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(anomaly_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get anomaly error: {str(e)}")
        return None

def get_all_anomalies_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search anomalies error: {str(e)}")
        return []
