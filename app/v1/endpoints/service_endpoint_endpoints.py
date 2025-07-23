from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.service_endpoint import (
    ServiceEndpointCreate,
    ServiceEndpointUpdate,
    ServiceEndpointInDB
)
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.service_endpoint_repository import ServiceEndpointRepository
from app.db.models.service_endpoint import ServiceEndpoint
from app.services.elasticsearch.service_endpoint_service import index_service_endpoint
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoints = ServiceEndpointRepository(db, redis).get_all()
    return success_response(serialize(endpoints, ServiceEndpointInDB), "Service endpoints fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoints = ServiceEndpointRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(endpoints, ServiceEndpointInDB), "Soft deleted service endpoints fetched successfully.")


@router.get("/{endpoint_id}")
def get_by_id(endpoint_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoint = ServiceEndpointRepository(db, redis).get_by_id(endpoint_id)
    if not endpoint:
        return error_response("Service endpoint not found", 404)
    return success_response(serialize(endpoint, ServiceEndpointInDB), "Service endpoint fetched successfully.")


@router.post("/")
def create(data: ServiceEndpointCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    endpoint = ServiceEndpointRepository(db, redis).create(data.dict())
    index_service_endpoint(endpoint)
    return success_response(serialize(endpoint, ServiceEndpointInDB), "Service endpoint created successfully.", 201)


@router.put("/{endpoint_id}")
def update(endpoint_id: UUID, data: ServiceEndpointUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ServiceEndpointRepository(db, redis).update(endpoint_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Service endpoint not found", 404)
    db.refresh(result)
    index_service_endpoint(result)
    return success_response(serialize(result, ServiceEndpointInDB), "Service endpoint updated successfully.")


@router.delete("/soft/{endpoint_id}")
def soft_delete(endpoint_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ServiceEndpointRepository(db, redis).soft_delete(endpoint_id)
    if not result:
        return error_response("Service endpoint not found", 404)
    return success_response(serialize(result, ServiceEndpointInDB), "Service endpoint soft deleted successfully.")


@router.put("/restore/{endpoint_id}")
def restore(endpoint_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ServiceEndpointRepository(db, redis).restore(endpoint_id)
    if not result:
        return error_response("Service endpoint not found", 404)
    return success_response(serialize(result, ServiceEndpointInDB), "Service endpoint restored successfully.")


@router.delete("/hard/{endpoint_id}")
def hard_delete(endpoint_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ServiceEndpointRepository(db, redis).hard_delete(endpoint_id)
    if not result:
        return error_response("Service endpoint not found", 404)
    return success_response(serialize(result, ServiceEndpointInDB), "Service endpoint permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = ServiceEndpointRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, ServiceEndpointInDB), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    endpoints = db.query(ServiceEndpoint).filter_by(is_deleted=False).all()
    for endpoint in endpoints:
        index_service_endpoint(endpoint)
    return success_response({"count": len(endpoints)}, "All service endpoints indexed to Elasticsearch.")
