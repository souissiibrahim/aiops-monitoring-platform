from app.services.elasticsearch.connection import get_elasticsearch_connection
from datetime import datetime

def format_datetime(dt):
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)

def index_incident(incident):
    doc = {
        "id": getattr(incident, "id", None),
        "title": getattr(incident, "title", ""),
        "description": getattr(incident, "description", ""),
        "status": getattr(incident, "status", ""),
        "severity": getattr(incident, "severity", ""),
        "created_at": format_datetime(getattr(incident, "created_at", "")),
        "updated_at": format_datetime(getattr(incident, "updated_at", ""))
    }   

    try:
        es = get_elasticsearch_connection()
        print(f"📤 Indexing document to Elasticsearch: {doc}")
        es.index(index="incidents", id=doc["id"], document=doc, request_timeout=10)
    except Exception as e:
        print(f"❌ Failed to index document to Elasticsearch: {e}")