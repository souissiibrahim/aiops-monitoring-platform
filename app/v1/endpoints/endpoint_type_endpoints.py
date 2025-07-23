from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.endpoint_type import (
    EndpointTypeCreate,
    EndpointTypeUpdate,
    EndpointTypeInDB,
)
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.endpoint_type_repository import EndpointTypeRepository
from app.db.models.endpoint_type import EndpointType
from app.services.elasticsearch.endpoint_type_service import index_endpoint_type
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoint_types = EndpointTypeRepository(db, redis).get_all()
    return success_response(serialize(endpoint_types, EndpointTypeInDB), "Endpoint types fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoint_types = EndpointTypeRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(endpoint_types, EndpointTypeInDB), "Soft deleted endpoint types fetched successfully.")


@router.get("/{endpoint_type_id}")
def get_by_id(endpoint_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EndpointTypeRepository(db, redis).get_by_id(endpoint_type_id)
    if not result:
        return error_response("Endpoint type not found", 404)
    return success_response(serialize(result, EndpointTypeInDB), "Endpoint type fetched successfully.")


@router.post("/")
def create(data: EndpointTypeCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoint_type = EndpointTypeRepository(db, redis).create(data.dict())
    try:
        index_endpoint_type(endpoint_type)
    except Exception as e:
        print(f"❌ Failed to index endpoint type after creation: {e}")
    return success_response(serialize(endpoint_type, EndpointTypeInDB), "Endpoint type created successfully.", 201)


@router.put("/{endpoint_type_id}")
def update(endpoint_type_id: UUID, data: EndpointTypeUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EndpointTypeRepository(db, redis).update(endpoint_type_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Endpoint type not found", 404)
    try:
        index_endpoint_type(result)
    except Exception as e:
        print(f"❌ Failed to index endpoint type after update: {e}")
    return success_response(serialize(result, EndpointTypeInDB), "Endpoint type updated successfully.")


@router.delete("/soft/{endpoint_type_id}")
def soft_delete(endpoint_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EndpointTypeRepository(db, redis).soft_delete(endpoint_type_id)
    if not result:
        return error_response("Endpoint type not found", 404)
    return success_response(serialize(result, EndpointTypeInDB), "Endpoint type soft deleted successfully.")


@router.put("/restore/{endpoint_type_id}")
def restore(endpoint_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EndpointTypeRepository(db, redis).restore(endpoint_type_id)
    if not result:
        return error_response("Endpoint type not found", 404)
    return success_response(serialize(result, EndpointTypeInDB), "Endpoint type restored successfully.")


@router.delete("/hard/{endpoint_type_id}")
def hard_delete(endpoint_type_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EndpointTypeRepository(db, redis).hard_delete(endpoint_type_id)
    if not result:
        return error_response("Endpoint type not found", 404)
    return success_response(serialize(result, EndpointTypeInDB), "Endpoint type permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = EndpointTypeRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, EndpointTypeInDB), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    endpoint_types = db.query(EndpointType).filter_by(is_deleted=False).all()
    count = 0
    for et in endpoint_types:
        try:
            index_endpoint_type(et)
            count += 1
        except Exception as e:
            print(f"❌ Failed to index endpoint type {et.id}: {e}")
    return success_response({"count": count}, "All endpoint types indexed to Elasticsearch.")
