from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.location import LocationCreate, LocationUpdate, LocationInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.location_repository import LocationRepository
from app.db.models.location import Location
from app.services.elasticsearch.location_service import index_location

router = APIRouter()

@router.get("/", response_model=list[LocationInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return LocationRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[LocationInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return LocationRepository(db, redis).get_all_soft_deleted()

@router.get("/{location_id}", response_model=LocationInDB)
def get_by_id(location_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    location = LocationRepository(db, redis).get_by_id(location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location

@router.post("/", response_model=LocationInDB)
def create(data: LocationCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    location = LocationRepository(db, redis).create(data.dict())
    try:
        index_location(location)
    except Exception as e:
        print(f"❌ Failed to index location: {e}")
    return location

@router.put("/{location_id}", response_model=LocationInDB)
def update(location_id: UUID, data: LocationUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = LocationRepository(db, redis).update(location_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    try:
        index_location(result)
    except Exception as e:
        print(f"❌ Failed to reindex location: {e}")
    return result

@router.delete("/soft/{location_id}", response_model=LocationInDB)
def soft_delete(location_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = LocationRepository(db, redis).soft_delete(location_id)
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result

@router.put("/restore/{location_id}", response_model=LocationInDB)
def restore(location_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = LocationRepository(db, redis).restore(location_id)
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result

@router.delete("/hard/{location_id}", response_model=LocationInDB)
def hard_delete(location_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = LocationRepository(db, redis).hard_delete(location_id)
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    return result

@router.get("/search/{keyword}", response_model=list[LocationInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return LocationRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    locations = db.query(Location).filter_by(is_deleted=False).all()
    for location in locations:
        index_location(location)
    return {"message": f"{len(locations)} locations indexed to Elasticsearch"}
