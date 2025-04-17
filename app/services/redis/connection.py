
from app.config import Settings  
import redis

def get_redis_connection():
    return redis.StrictRedis(
        host=Settings.REDIS_HOST,
        port=Settings.REDIS_PORT,
        password=Settings.REDIS_PASSWORD,
        decode_responses=True
    )

def test_redis_connection():
    try:
        r = get_redis_connection()
        r.set("test", "ok")
        return "✅ Redis Connected Successfully"
    except Exception as e:
        return f"❌ Redis Connection Failed: {str(e)}"