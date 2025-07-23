from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.v1.schemas.team_endpoint_ownership import (
    TeamEndpointOwnershipInDB,
    TeamEndpointOwnershipCreate,
    TeamEndpointOwnershipUpdate,
)
from app.db.repositories.team_endpoint_ownership_repository import TeamEndpointOwnershipRepository
from app.db.models.team_endpoint_ownership import TeamEndpointOwnership as TeamEndpointOwnershipModel
from app.services.elasticsearch.team_endpoint_ownership_service import index_team_endpoint_ownership
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    ownerships = TeamEndpointOwnershipRepository(db, redis).get_all()
    return success_response(serialize(ownerships, TeamEndpointOwnershipInDB), "Ownerships fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    ownerships = TeamEndpointOwnershipRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(ownerships, TeamEndpointOwnershipInDB), "Soft-deleted ownerships fetched successfully.")


@router.get("/{ownership_id}")
def get_by_id(ownership_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    ownership = TeamEndpointOwnershipRepository(db, redis).get_by_id(ownership_id)
    if not ownership:
        return error_response("Ownership not found", 404)
    return success_response(serialize(ownership, TeamEndpointOwnershipInDB), "Ownership fetched successfully.")


@router.post("/")
def create(data: TeamEndpointOwnershipCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    ownership = TeamEndpointOwnershipRepository(db, redis).create(data.dict())
    index_team_endpoint_ownership(ownership)
    return success_response(serialize(ownership, TeamEndpointOwnershipInDB), "Ownership created successfully.", 201)


@router.put("/{ownership_id}")
def update(
    ownership_id: UUID,
    data: TeamEndpointOwnershipUpdate,
    db: Session = Depends(get_db),
    redis=Depends(get_redis_connection),
):
    updated = TeamEndpointOwnershipRepository(db, redis).update(ownership_id, data.dict(exclude_unset=True))
    if not updated:
        return error_response("Ownership not found", 404)
    db.refresh(updated)
    index_team_endpoint_ownership(updated)
    return success_response(serialize(updated, TeamEndpointOwnershipInDB), "Ownership updated successfully.")


@router.delete("/soft/{ownership_id}")
def soft_delete(ownership_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamEndpointOwnershipRepository(db, redis).soft_delete(ownership_id)
    if not result:
        return error_response("Ownership not found", 404)
    return success_response(serialize(result, TeamEndpointOwnershipInDB), "Ownership soft deleted successfully.")


@router.put("/restore/{ownership_id}")
def restore(ownership_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamEndpointOwnershipRepository(db, redis).restore(ownership_id)
    if not result:
        return error_response("Ownership not found", 404)
    return success_response(serialize(result, TeamEndpointOwnershipInDB), "Ownership restored successfully.")


@router.delete("/hard/{ownership_id}")
def hard_delete(ownership_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamEndpointOwnershipRepository(db, redis).hard_delete(ownership_id)
    if not result:
        return error_response("Ownership not found", 404)
    return success_response(serialize(result, TeamEndpointOwnershipInDB), "Ownership permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = TeamEndpointOwnershipRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, TeamEndpointOwnershipInDB), f"Search results for '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    ownerships = db.query(TeamEndpointOwnershipModel).filter_by(is_deleted=False).all()
    for o in ownerships:
        index_team_endpoint_ownership(o)
    return success_response({"count": len(ownerships)}, "All ownerships indexed to Elasticsearch.")
