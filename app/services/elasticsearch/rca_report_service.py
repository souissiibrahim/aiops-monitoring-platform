from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from datetime import datetime

es = get_elasticsearch_connection()
INDEX_NAME = "rca_reports"

def index_rca_report(rca_report):
    try:
        doc = {
            "id": rca_report.id,
            "incident_id": rca_report.incident_id,
            "root_cause": rca_report.root_cause or "",
            "confidence": rca_report.confidence,
            "recommendation": rca_report.recommendation or "",
            "created_at": rca_report.created_at.isoformat() if rca_report.created_at else None,
            "updated_at": rca_report.updated_at.isoformat() if rca_report.updated_at else None,
            "deleted_at": rca_report.deleted_at.isoformat() if rca_report.deleted_at else None
        }

        es.index(
            index=INDEX_NAME,
            id=rca_report.id,
            body=doc,
            refresh=True
        )
        print(f"✅ RCAReport {rca_report.id} indexed.")
    except Exception as e:
        print(f"❌ Indexing RCAReport error: {e}")


def get_rca_report_from_es(rca_id):
    try:
        result = es.get(index=INDEX_NAME, id=rca_id)
        source = result["_source"]
        source["created_at"] = datetime.fromisoformat(source["created_at"])
        source["updated_at"] = datetime.fromisoformat(source["updated_at"])
        source["deleted_at"] = datetime.fromisoformat(source["deleted_at"]) if source["deleted_at"] else None
        return source
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get RCAReport error: {str(e)}")
        return None


def get_all_rca_reports_from_es():
    try:
        result = es.search(
            index=INDEX_NAME,
            body={"query": {"match_all": {}}},
            size=1000
        )
        return [
            {
                **hit["_source"],
                "created_at": datetime.fromisoformat(hit["_source"]["created_at"]),
                "updated_at": datetime.fromisoformat(hit["_source"]["updated_at"]),
                "deleted_at": datetime.fromisoformat(hit["_source"]["deleted_at"])
                    if hit["_source"]["deleted_at"] else None
            }
            for hit in result["hits"]["hits"]
        ]
    except Exception as e:
        print(f"[ES] Search RCAReports error: {str(e)}")
        return []
