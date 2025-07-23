from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "rca_analysis"

def serialize_rca(rca):
    return {
        "rca_id": str(rca.rca_id),
        "incident_id": str(rca.incident_id),
        "analysis_method": rca.analysis_method,
        "root_cause_node_id": str(rca.root_cause_node_id) if rca.root_cause_node_id else None,
        "confidence_score": rca.confidence_score,
        "contributing_factors": rca.contributing_factors,
        "recommendations": rca.recommendations,
        "analysis_timestamp": rca.analysis_timestamp.isoformat(),
        "analyst_team_id": str(rca.analyst_team_id) if rca.analyst_team_id else None,
        "created_at": rca.created_at.isoformat() if rca.created_at else None,
        "updated_at": rca.updated_at.isoformat() if rca.updated_at else None,
        "deleted_at": rca.deleted_at.isoformat() if rca.deleted_at else None,
    }

def index_rca(rca):
    try:
        doc = serialize_rca(rca)
        es.index(index=INDEX_NAME, id=str(rca.rca_id), body=doc, refresh=True)
        print(f"✅ RCA {rca.rca_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing RCA {rca.rca_id}: {e}")

def get_rca_from_es(rca_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(rca_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get RCA error: {str(e)}")
        return None

def get_all_rcas_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search RCA error: {str(e)}")
        return []
