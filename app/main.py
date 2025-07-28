from fastapi import FastAPI
from app.api.router import router as api_router
from app.services.redis.connection import test_redis_connection
from app.services.elasticsearch.connection import test_elasticsearch_connection
from app.services.postgres.connection import test_postgres_connection
from app.db.session import engine, Base, update_existing_tables
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def initialize_database():
    Base.metadata.create_all(bind=engine)
    update_existing_tables()

app.include_router(api_router)

@app.get("/test")
def test_connections():
    return {
        "redis": test_redis_connection(),
        "elasticsearch": test_elasticsearch_connection(),
        "postgres": test_postgres_connection()
    }
