from fastapi import APIRouter, Depends, HTTPException
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

router = APIRouter()

@router.get("/", response_model=list[DependencyGraphInDB])
def get_all(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return DependencyGraphRepository(db, redis).get_all()

@router.get("/deleted", response_model=list[DependencyGraphInDB])
def get_all_soft_deleted(db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    return DependencyGraphRepository(db, redis).get_all_soft_deleted()

@router.get("/{dependency_id}", response_model=DependencyGraphInDB)
def get_by_id(dependency_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    dependency = DependencyGraphRepository(db, redis).get_by_id(dependency_id)
    if not dependency:
        raise HTTPException(status_code=404, detail="Dependency not found")
    return dependency

@router.post("/", response_model=DependencyGraphInDB)
def create(data: DependencyGraphCreate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    dependency = DependencyGraphRepository(db, redis).create(data.dict())
    index_dependency_graph(dependency)
    return dependency

@router.put("/{dependency_id}", response_model=DependencyGraphInDB)
def update(dependency_id: UUID, data: DependencyGraphUpdate, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = DependencyGraphRepository(db, redis).update(dependency_id, data.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Dependency not found")
    db.refresh(result)
    index_dependency_graph(result)
    return result

@router.delete("/soft/{dependency_id}", response_model=DependencyGraphInDB)
def soft_delete(dependency_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = DependencyGraphRepository(db, redis).soft_delete(dependency_id)
    if not result:
        raise HTTPException(status_code=404, detail="Dependency not found")
    return result

@router.put("/restore/{dependency_id}", response_model=DependencyGraphInDB)
def restore(dependency_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = DependencyGraphRepository(db, redis).restore(dependency_id)
    if not result:
        raise HTTPException(status_code=404, detail="Dependency not found")
    return result

@router.delete("/hard/{dependency_id}", response_model=DependencyGraphInDB)
def hard_delete(dependency_id: UUID, db: Session = Depends(get_db), redis=Depends(get_redis_connection)):
    result = DependencyGraphRepository(db, redis).hard_delete(dependency_id)
    if not result:
        raise HTTPException(status_code=404, detail="Dependency not found")
    return result

@router.get("/search/{keyword}", response_model=list[DependencyGraphInDB])
def search(keyword: str, db: Session = Depends(get_db), redis=Depends(get_redis_connection), es=Depends(get_elasticsearch_connection)):
    return DependencyGraphRepository(db, redis).search(keyword, es)

@router.post("/index-all")
def index_all_to_elasticsearch(db: Session = Depends(get_db)):
    dependencies = db.query(DependencyGraph).filter_by(is_deleted=False).all()
    for dependency in dependencies:
        index_dependency_graph(dependency)
    return {"message": f"{len(dependencies)} dependency graph entries indexed to Elasticsearch"}
