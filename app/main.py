from fastapi import FastAPI
from app.services.redis.connection import test_redis_connection
from app.services.elasticsearch.connection import test_elasticsearch_connection
from app.services.postgres.connection import test_postgres_connection

app = FastAPI()

@app.get("/test")
def test_connections():
    return {
        "redis": test_redis_connection,
        "elasticsearch": test_elasticsearch_connection(),
        "postgres": test_postgres_connection()
    }
