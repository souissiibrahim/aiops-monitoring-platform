from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.v1.schemas.dependency_graph import (
    DependencyGraphCreate,
    DependencyGraphUpdate,
    DependencyGraphInDB,
)
from app.db.session import get_db
from app.services.redis.connection import get_redis_connection
from app.services.elasticsearch.connection import get_elasticsearch_connection
from app.db.models.dependency_graph import DependencyGraph
from app.db.repositories.dependency_graph_repository import DependencyGraphRepository
from app.services.elasticsearch.dependency_graph_service import index_dependency_graph
from app.utils.response import success_response, error_response

router = APIRouter()

def serialize(obj, schema):
    if isinstance(obj, list):
        return [schema.from_orm(o).model_dump(mode="json") for o in obj]
    return schema.from_orm(obj).model_dump(mode="json")


@router.get("/")
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    dependencies = DependencyGraphRepository(db, redis).get_all()
    return success_response(serialize(dependencies, DependencyGraphInDB), "Dependency graph entries fetched successfully.")


@router.get("/deleted")
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    dependencies = DependencyGraphRepository(db, redis).get_all_soft_deleted()
    return success_response(serialize(dependencies, DependencyGraphInDB), "Soft deleted dependency graph entries fetched successfully.")


@router.get("/{dependency_id}")
def get_by_id(dependency_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    dependency = DependencyGraphRepository(db, redis).get_by_id(dependency_id)
    if not dependency:
        return error_response("Dependency not found", 404)
    return success_response(serialize(dependency, DependencyGraphInDB), "Dependency graph entry fetched successfully.")


@router.post("/")
def create(data: DependencyGraphCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    dependency = DependencyGraphRepository(db, redis).create(data.dict())
    try:
        index_dependency_graph(dependency)
    except Exception as e:
        print(f"❌ Failed to index dependency graph entry: {e}")
    return success_response(serialize(dependency, DependencyGraphInDB), "Dependency graph entry created successfully.", 201)


@router.put("/{dependency_id}")
def update(dependency_id: UUID, data: DependencyGraphUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = DependencyGraphRepository(db, redis).update(dependency_id, data.dict(exclude_unset=True))
    if not result:
        return error_response("Dependency not found", 404)
    try:
        db.refresh(result)
        index_dependency_graph(result)
    except Exception as e:
        print(f"❌ Failed to reindex dependency graph entry: {e}")
    return success_response(serialize(result, DependencyGraphInDB), "Dependency graph entry updated successfully.")


@router.delete("/soft/{dependency_id}")
def soft_delete(dependency_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = DependencyGraphRepository(db, redis).soft_delete(dependency_id)
    if not result:
        return error_response("Dependency not found", 404)
    return success_response(serialize(result, DependencyGraphInDB), "Dependency graph entry soft deleted successfully.")


@router.put("/restore/{dependency_id}")
def restore(dependency_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = DependencyGraphRepository(db, redis).restore(dependency_id)
    if not result:
        return error_response("Dependency not found", 404)
    return success_response(serialize(result, DependencyGraphInDB), "Dependency graph entry restored successfully.")


@router.delete("/hard/{dependency_id}")
def hard_delete(dependency_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = DependencyGraphRepository(db, redis).hard_delete(dependency_id)
    if not result:
        return error_response("Dependency not found", 404)
    return success_response(serialize(result, DependencyGraphInDB), "Dependency graph entry permanently deleted successfully.")


@router.get("/search/{keyword}")
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    results = DependencyGraphRepository(db, redis).search(keyword, es)
    return success_response(serialize(results, DependencyGraphInDB), f"Search results for keyword '{keyword}'.")


@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    dependencies = db.query(DependencyGraph).filter_by(is_deleted=False).all()
    count = 0
    for dependency in dependencies:
        try:
            index_dependency_graph(dependency)
            count += 1
        except Exception as e:
            print(f"❌ Failed to index dependency graph {dependency.id}: {e}")
    return success_response({"count": count}, "All dependency graph entries indexed to Elasticsearch.")
