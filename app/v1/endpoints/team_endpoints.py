from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.team import TeamCreate, TeamUpdate, TeamInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.repositories.team_repository import TeamRepository
from app.db.models.team import Team
from app.services.elasticsearch.team_service import index_team
from app.utils.response import success_response, error_response

router = APIRouter()

def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    teams = TeamRepository(db, redis).get_all()
    return success_response(serialize(teams, TeamInDB), "Teams fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    teams = TeamRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(teams, TeamInDB), "Soft deleted teams fetched successfully.")


@router.get("/{team_id}")
def get_by_id(team_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    team = TeamRepository(db, redis).get_by_id(team_id)
    if not team:
        return error_response("Team not found", 404)
    return success_response(serialize(team, TeamInDB), "Team fetched successfully.")


@router.post("/")
def create(data: TeamCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    team = TeamRepository(db, redis).create(data.dict())
    try:
        index_team(team)
    except Exception as e:
        print(f"❌ Failed to index team: {e}")
    return success_response(serialize(team, TeamInDB), "Team created successfully.", 201)


@router.put("/{team_id}")
def update(team_id: UUID, data: TeamUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamRepository(db, redis).update(team_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Team not found", 404)
    try:
        db.refresh(result)
        index_team(result)
    except Exception as e:
        print(f"❌ Failed to reindex team: {e}")
    return success_response(serialize(result, TeamInDB), "Team updated successfully.")


@router.delete("/soft/{team_id}")
def soft_delete(team_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamRepository(db, redis).soft_delete(team_id)
    if not result:
        return error_response("Team not found", 404)
    return success_response(serialize(result, TeamInDB), "Team soft deleted successfully.")


@router.put("/restore/{team_id}")
def restore(team_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamRepository(db, redis).restore(team_id)
    if not result:
        return error_response("Team not found", 404)
    return success_response(serialize(result, TeamInDB), "Team restored successfully.")


@router.delete("/hard/{team_id}")
def hard_delete(team_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = TeamRepository(db, redis).hard_delete(team_id)
    if not result:
        return error_response("Team not found", 404)
    return success_response(serialize(result, TeamInDB), "Team permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = TeamRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, TeamInDB), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    teams = db.query(Team).filter_by(is_deleted=False).all()
    count = 0
    for team in teams:
        try:
            index_team(team)
            count += 1
        except Exception as e:
            print(f"❌ Failed to index team {team.id}: {e}")
    return success_response({"count": count}, "All teams indexed to Elasticsearch.")
