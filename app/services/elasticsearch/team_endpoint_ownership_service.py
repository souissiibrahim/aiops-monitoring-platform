from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID
from app.db.models.team_endpoint_ownership import TeamEndpointOwnership

es = get_elasticsearch_connection()
INDEX_NAME = "team_endpoint_ownerships"


def serialize_team_endpoint_ownership(ownership: TeamEndpointOwnership) -> dict:
    return {
        "ownership_id": str(ownership.ownership_id),
        "team_id": str(ownership.team_id),
        "source_id": str(ownership.source_id),
        "is_primary": ownership.is_primary,
        "start_date": ownership.start_date.isoformat() if ownership.start_date else None,
        "end_date": ownership.end_date.isoformat() if ownership.end_date else None,
        "created_at": ownership.created_at.isoformat() if ownership.created_at else None,
        "updated_at": ownership.updated_at.isoformat() if ownership.updated_at else None,
        "deleted_at": ownership.deleted_at.isoformat() if ownership.deleted_at else None,
        "is_deleted": ownership.is_deleted,
    }


def index_team_endpoint_ownership(ownership: TeamEndpointOwnership):
    try:
        doc = serialize_team_endpoint_ownership(ownership)
        es.index(index=INDEX_NAME, id=str(ownership.ownership_id), body=doc, refresh=True)
        print(f"✅ TeamEndpointOwnership {ownership.ownership_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing TeamEndpointOwnership {ownership.ownership_id}: {e}")


def get_team_endpoint_ownership_from_es(ownership_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(ownership_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get TeamEndpointOwnership error: {str(e)}")
        return None


def get_all_team_endpoint_ownerships_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search TeamEndpointOwnerships error: {str(e)}")
        return []
