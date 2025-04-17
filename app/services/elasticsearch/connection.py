# app/services/elasticsearch/connection.py
from elasticsearch import Elasticsearch
from app.config import Settings  

def get_elasticsearch_connection():
    return Elasticsearch(
        [Settings.ELASTICSEARCH_HOST],
        http_auth=(Settings.ELASTICSEARCH_USER, Settings.ELASTICSEARCH_PASSWORD),
        verify_certs=False
    )

def test_elasticsearch_connection():
    try:
        es = get_elasticsearch_connection()
        info = es.info()
        return f"✅ Elasticsearch Connected: {info['version']['number']}"
    except Exception as e:
        return f"❌ Elasticsearch Connection Failed: {str(e)}"