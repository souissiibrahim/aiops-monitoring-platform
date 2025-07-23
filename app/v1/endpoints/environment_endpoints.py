from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.environment import EnvironmentCreate, EnvironmentUpdate, EnvironmentInDB
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.models.environment import Environment
from app.db.repositories.environment_repository import EnvironmentRepository
from app.services.elasticsearch.environment_service import index_environment
from app.utils.response import success_response, error_response

router = APIRouter()


def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    envs = EnvironmentRepository(db, redis).get_all()
    return success_response(serialize(envs, EnvironmentInDB), "Environments fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    envs = EnvironmentRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(envs, EnvironmentInDB), "Soft deleted environments fetched successfully.")


@router.get("/{environment_id}")
def get_by_id(environment_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    env = EnvironmentRepository(db, redis).get_by_id(environment_id)
    if not env:
        return error_response("Environment not found", 404)
    return success_response(serialize(env, EnvironmentInDB), "Environment fetched successfully.")


@router.post("/")
def create(data: EnvironmentCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    env = EnvironmentRepository(db, redis).create(data.dict())
    try:
        index_environment(env)
    except Exception as e:
        print(f"❌ Failed to index environment after creation: {e}")
    return success_response(serialize(env, EnvironmentInDB), "Environment created successfully.", 201)


@router.put("/{environment_id}")
def update(environment_id: UUID, data: EnvironmentUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EnvironmentRepository(db, redis).update(environment_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Environment not found", 404)
    try:
        index_environment(result)
    except Exception as e:
        print(f"❌ Failed to index environment after update: {e}")
    return success_response(serialize(result, EnvironmentInDB), "Environment updated successfully.")


@router.delete("/soft/{environment_id}")
def soft_delete(environment_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EnvironmentRepository(db, redis).soft_delete(environment_id)
    if not result:
        return error_response("Environment not found", 404)
    return success_response(serialize(result, EnvironmentInDB), "Environment soft deleted successfully.")


@router.put("/restore/{environment_id}")
def restore(environment_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EnvironmentRepository(db, redis).restore(environment_id)
    if not result:
        return error_response("Environment not found", 404)
    return success_response(serialize(result, EnvironmentInDB), "Environment restored successfully.")


@router.delete("/hard/{environment_id}")
def hard_delete(environment_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = EnvironmentRepository(db, redis).hard_delete(environment_id)
    if not result:
        return error_response("Environment not found", 404)
    return success_response(serialize(result, EnvironmentInDB), "Environment permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = EnvironmentRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, EnvironmentInDB), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    environments = db.query(Environment).filter_by(is_deleted=False).all()
    success_count = 0
    for env in environments:
        try:
            index_environment(env)
            success_count += 1
        except Exception as e:
            print(f"❌ Failed to index environment {env.id}: {e}")
    return success_response({"count": success_count}, "All environments indexed to Elasticsearch.")
