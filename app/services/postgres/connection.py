# app/services/postgres/connection.py

import psycopg2
from app.config import Settings

def get_postgres_connection():
    return psycopg2.connect(
        host=Settings.POSTGRES_HOST,
        port=Settings.POSTGRES_PORT,
        user=Settings.POSTGRES_USER,
        password=Settings.POSTGRES_PASSWORD,
        dbname=Settings.POSTGRES_DB
    )

def test_postgres_connection():
    try:
        conn = get_postgres_connection()
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        cur.close()
        conn.close()
        return f"✅ PostgreSQL Connected: {version}"
    except Exception as e:
        return f"❌ PostgreSQL Connection Failed: {str(e)}"
