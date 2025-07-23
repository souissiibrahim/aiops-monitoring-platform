from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from app.config import Settings
from app.db.base import Base

from app.db.models import (
    incident,
    incident_status,
    incident_type,
    severity_level,
    rca_analysis,
    telemetry_source,
    environment,
    service,
    anomaly,
    prediction,
    response_action,
    audit_log,
    runbook,
    runbook_step,
    team,
    team_endpoint_ownership,
    endpoint_type,
    location,
    service_endpoint,
    dependency_graph,
    shap_explanation,
    model
)

SQLALCHEMY_DATABASE_URL = (
    f"postgresql://{Settings.POSTGRES_USER}:{Settings.POSTGRES_PASSWORD}"
    f"@{Settings.POSTGRES_HOST}:{Settings.POSTGRES_PORT}/{Settings.POSTGRES_DB}"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def update_existing_tables():
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table_name, table in Base.metadata.tables.items():
            if not inspector.has_table(table_name):
                continue
            existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
            for column in table.columns:
                if column.name not in existing_columns:
                    col_type = str(column.type.compile(dialect=engine.dialect))
                    sql = f'ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type};'
                    try:
                        conn.execute(text(sql))
                        print(f"✅ Added column '{column.name}' to '{table_name}'")
                    except Exception as e:
                        print(f"❌ Failed to add column '{column.name}' to '{table_name}': {e}")
