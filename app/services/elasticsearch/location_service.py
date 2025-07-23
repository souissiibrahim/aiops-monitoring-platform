from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "locations"

def serialize_location(location):
    return {
        "location_id": str(location.location_id),
        "name": location.name,
        "region_code": location.region_code or "",
        "country": location.country or "",
        "latitude": location.latitude,
        "longitude": location.longitude,
        "created_at": location.created_at.isoformat() if location.created_at else None,
        "updated_at": location.updated_at.isoformat() if location.updated_at else None,
        "deleted_at": location.deleted_at.isoformat() if location.deleted_at else None,
    }

def index_location(location):
    try:
        doc = serialize_location(location)
        es.index(index=INDEX_NAME, id=str(location.location_id), body=doc, refresh=True)
        print(f"✅ Location {location.location_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing location {location.location_id}: {e}")

def get_location_from_es(location_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(location_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get location error: {str(e)}")
        return None

def get_all_locations_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search locations error: {str(e)}")
        return []
