from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.service import ServiceCreate, ServiceUpdate, ServiceInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.service_repository import ServiceRepository
from app.db.models.service import Service
from app.services.elasticsearch.service_service import index_service
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    services = ServiceRepository(db, redis).get_all()
    return success_response(serialize(services, ServiceInDB), "Services fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    services = ServiceRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(services, ServiceInDB), "Soft deleted services fetched successfully.")


@router.get("/{service_id}")
def get_by_id(service_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    service = ServiceRepository(db, redis).get_by_id(service_id)
    if not service:
        return error_response("Service not found", 404)
    return success_response(serialize(service, ServiceInDB), "Service fetched successfully.")


@router.post("/")
def create(data: ServiceCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    service = ServiceRepository(db, redis).create(data.dict())
    index_service(service)
    return success_response(serialize(service, ServiceInDB), "Service created successfully.", 201)


@router.put("/{service_id}")
def update(service_id: UUID, data: ServiceUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ServiceRepository(db, redis).update(service_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Service not found", 404)
    db.refresh(result)
    index_service(result)
    return success_response(serialize(result, ServiceInDB), "Service updated successfully.")


@router.delete("/soft/{service_id}")
def soft_delete(service_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ServiceRepository(db, redis).soft_delete(service_id)
    if not result:
        return error_response("Service not found", 404)
    return success_response(serialize(result, ServiceInDB), "Service soft deleted successfully.")


@router.put("/restore/{service_id}")
def restore(service_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ServiceRepository(db, redis).restore(service_id)
    if not result:
        return error_response("Service not found", 404)
    return success_response(serialize(result, ServiceInDB), "Service restored successfully.")


@router.delete("/hard/{service_id}")
def hard_delete(service_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = ServiceRepository(db, redis).hard_delete(service_id)
    if not result:
        return error_response("Service not found", 404)
    return success_response(serialize(result, ServiceInDB), "Service permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = ServiceRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, ServiceInDB), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    services = db.query(Service).filter_by(is_deleted=False).all()
    for service in services:
        index_service(service)
    return success_response({"count": len(services)}, "All services indexed to Elasticsearch.")
