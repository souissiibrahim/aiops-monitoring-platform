from fastapi import APIRouter, Depends, HTTPException
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

router = APIRouter()


@router.get("/", response_model=list[TeamEndpointOwnershipInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return TeamEndpointOwnershipRepository(db, redis).get_all()


@router.get("/deleted", response_model=list[TeamEndpointOwnershipInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return TeamEndpointOwnershipRepository(db, redis).get_all_soft_deleted()


@router.get("/{ownership_id}", response_model=TeamEndpointOwnershipInDB)
def get_by_id(ownership_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    ownership = TeamEndpointOwnershipRepository(db, redis).get_by_id(ownership_id)
    if not ownership:
        raise HTTPException(status_code=404, detail="Ownership not found")
    return ownership


@router.post("/", response_model=TeamEndpointOwnershipInDB)
def create(data: TeamEndpointOwnershipCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    ownership = TeamEndpointOwnershipRepository(db, redis).create(data.dict())
    index_team_endpoint_ownership(ownership)
    return ownership


@router.put("/{ownership_id}", response_model=TeamEndpointOwnershipInDB)
def update(
    ownership_id: UUID,
    data: TeamEndpointOwnershipUpdate,
    db: Session = Depends(get_db),
    redis=Depends(get_redis_connection),
):
    updated = TeamEndpointOwnershipRepository(db, redis).update(ownership_id, data.dict(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Ownership not found")
    db.refresh(updated)
    index_team_endpoint_ownership(updated)
    return updated


@router.delete("/soft/{ownership_id}", response_model=TeamEndpointOwnershipInDB)
def soft_delete(ownership_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamEndpointOwnershipRepository(db, redis).soft_delete(ownership_id)
    if not result:
        raise HTTPException(status_code=404, detail="Ownership not found")
    return result


@router.put("/restore/{ownership_id}", response_model=TeamEndpointOwnershipInDB)
def restore(ownership_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamEndpointOwnershipRepository(db, redis).restore(ownership_id)
    if not result:
        raise HTTPException(status_code=404, detail="Ownership not found")
    return result


@router.delete("/hard/{ownership_id}", response_model=TeamEndpointOwnershipInDB)
def hard_delete(ownership_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamEndpointOwnershipRepository(db, redis).hard_delete(ownership_id)
    if not result:
        raise HTTPException(status_code=404, detail="Ownership not found")
    return result


@router.get("/search/{keyword}", response_model=list[TeamEndpointOwnershipInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return TeamEndpointOwnershipRepository(db, redis).search(keyword, es)


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    ownerships = db.query(TeamEndpointOwnershipModel).filter_by(is_deleted=False).all()
    for o in ownerships:
        index_team_endpoint_ownership(o)
    return {"message": f"{len(ownerships)} team endpoint ownerships indexed to Elasticsearch"}
