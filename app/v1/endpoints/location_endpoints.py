from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.location import LocationCreate, LocationUpdate, LocationInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.location_repository import LocationRepository
from app.db.models.location import Location
from app.services.elasticsearch.location_service import index_location
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    locations = LocationRepository(db, redis).get_all()
    return success_response(serialize(locations, LocationInDB), "Locations fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    locations = LocationRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(locations, LocationInDB), "Soft deleted locations fetched successfully.")


@router.get("/{location_id}")
def get_by_id(location_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    location = LocationRepository(db, redis).get_by_id(location_id)
    if not location:
        return error_response("Location not found", 404)
    return success_response(serialize(location, LocationInDB), "Location fetched successfully.")


@router.post("/")
def create(data: LocationCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    location = LocationRepository(db, redis).create(data.dict())
    try:
        index_location(location)
    except Exception as e:
        print(f"❌ Failed to index location: {e}")
    return success_response(serialize(location, LocationInDB), "Location created successfully.", 201)


@router.put("/{location_id}")
def update(location_id: UUID, data: LocationUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = LocationRepository(db, redis).update(location_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Location not found", 404)
    try:
        index_location(result)
    except Exception as e:
        print(f"❌ Failed to reindex location: {e}")
    return success_response(serialize(result, LocationInDB), "Location updated successfully.")


@router.delete("/soft/{location_id}")
def soft_delete(location_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = LocationRepository(db, redis).soft_delete(location_id)
    if not result:
        return error_response("Location not found", 404)
    return success_response(serialize(result, LocationInDB), "Location soft deleted successfully.")


@router.put("/restore/{location_id}")
def restore(location_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = LocationRepository(db, redis).restore(location_id)
    if not result:
        return error_response("Location not found", 404)
    return success_response(serialize(result, LocationInDB), "Location restored successfully.")


@router.delete("/hard/{location_id}")
def hard_delete(location_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = LocationRepository(db, redis).hard_delete(location_id)
    if not result:
        return error_response("Location not found", 404)
    return success_response(serialize(result, LocationInDB), "Location permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = LocationRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, LocationInDB), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    locations = db.query(Location).filter_by(is_deleted=False).all()
    count = 0
    for location in locations:
        try:
            index_location(location)
            count += 1
        except Exception as e:
            print(f"❌ Failed to index location {location.id}: {e}")
    return success_response({"count": count}, "All locations indexed to Elasticsearch.")
