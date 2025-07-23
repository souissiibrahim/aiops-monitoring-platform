from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.team import TeamCreate, TeamUpdate, TeamInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.team_repository import TeamRepository
from app.db.models.team import Team
from app.services.elasticsearch.team_service import index_team

router = APIRouter()

@router.get("/", response_model=list[TeamInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return TeamRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[TeamInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return TeamRepository(db, redis).get_all_soft_deleted()

@router.get("/{team_id}", response_model=TeamInDB)
def get_by_id(team_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    team = TeamRepository(db, redis).get_by_id(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team

@router.post("/", response_model=TeamInDB)
def create(data: TeamCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    team = TeamRepository(db, redis).create(data.dict())
    index_team(team)
    return team

@router.put("/{team_id}", response_model=TeamInDB)
def update(team_id: UUID, data: TeamUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamRepository(db, redis).update(team_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Team not found")
    db.refresh(result)
    index_team(result)
    return result

@router.delete("/soft/{team_id}", response_model=TeamInDB)
def soft_delete(team_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamRepository(db, redis).soft_delete(team_id)
    if not result:
        raise HTTPException(status_code=404, detail="Team not found")
    return result

@router.put("/restore/{team_id}", response_model=TeamInDB)
def restore(team_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamRepository(db, redis).restore(team_id)
    if not result:
        raise HTTPException(status_code=404, detail="Team not found")
    return result

@router.delete("/hard/{team_id}", response_model=TeamInDB)
def hard_delete(team_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamRepository(db, redis).hard_delete(team_id)
    if not result:
        raise HTTPException(status_code=404, detail="Team not found")
    return result

@router.get("/search/{keyword}", response_model=list[TeamInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return TeamRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    teams = db.query(Team).filter_by(is_deleted=False).all()
    for team in teams:
        index_team(team)
    return {"message": f"{len(teams)} teams indexed to Elasticsearch"}
