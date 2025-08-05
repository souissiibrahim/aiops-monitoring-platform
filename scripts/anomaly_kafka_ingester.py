import json
import time
from datetime import datetime
from uuid import UUID
from kafka import KafkaConsumer
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.repositories.anomaly_repository import AnomalyRepository
from app.db.repositories.incident_repository import IncidentRepository
from app.db.models.anomaly import Anomaly
from app.db.models.incident import Incident
from app.db.models.telemetry_source import TelemetrySource
from app.db.models.service import Service
from app.db.models.incident_type import IncidentType
from app.db.models.severity_level import SeverityLevel
from app.db.models.service_endpoint import ServiceEndpoint
from app.services.elasticsearch.anomaly_service import index_anomaly
from app.db.models.incident_status import IncidentStatus


KAFKA_TOPIC = "anomalies"
KAFKA_BOOTSTRAP = "localhost:29092"

consumer = KafkaConsumer(
    KAFKA_TOPIC,
    bootstrap_servers=KAFKA_BOOTSTRAP,
    group_id="anomaly-ingester",
    auto_offset_reset="latest",
    enable_auto_commit=True,
    value_deserializer=lambda m: m.decode("utf-8")
)

print("🚀 Anomaly Kafka ingester running...")

# Hardcoded mapping for now
HARDCODED_SOURCE_ID = UUID("a9783660-6107-4a78-a5fc-9333cd786952")

def get_source_id_by_metric(db: Session, metric: str) -> UUID:
    return HARDCODED_SOURCE_ID

def get_incident_type_id(db: Session, metric: str) -> UUID:
    itype = db.query(IncidentType).filter(IncidentType.name.ilike(f"%{metric}%")).first()
    return itype.incident_type_id if itype else None

def get_default_status_id(db: Session) -> UUID:
    status = db.query(IncidentStatus).filter_by(name="Open").first()
    return status.status_id if status else None

def get_severity_id(db: Session, value: float, confidence: float) -> UUID:
    if value > 0.9 or confidence > 0.95:
        name = "Critical"
    elif value > 0.6:
        name = "High"
    elif value > 0.3:
        name = "Medium"
    else:
        name = "Low"
    level = db.query(SeverityLevel).filter_by(name=name).first()
    return level.severity_level_id if level else None

while True:
    db: Session = SessionLocal()
    repo = AnomalyRepository(db, None)
    incident_repo = IncidentRepository(db, None)
    try:
        for msg in consumer:
            try:
                data = json.loads(msg.value)
            except Exception as e:
                print(f"❌ Invalid JSON: {e} | Raw: {msg}")
                continue

            print("📥 Received:", data)

            metric = data.get("metric_name")
            try:
                value = float(data["value"])
                confidence = float(data.get("confidence", 1.0))
                ts = datetime.utcfromtimestamp(float(data["timestamp"]))
            except Exception as e:
                print(f"❌ Invalid data format: {e}")
                continue

            source_id = get_source_id_by_metric(db, metric)
            if not source_id:
                print("❌ No source_id found.")
                continue

            exists = db.query(Anomaly).filter_by(
                source_id=source_id,
                metric_type=metric,
                timestamp=ts,
                value=value
            ).first()
            if exists:
                print("⚠️ Duplicate anomaly.")
                continue

            anomaly = repo.create({
                "source_id": source_id,
                "metric_type": metric,
                "value": value,
                "confidence_score": confidence,
                "timestamp": ts,
                "detection_method": "AutoEncoder",
                "anomaly_metadata": {
                    "collection_delay": data.get("collection_delay"),
                    "anomaly_score": data.get("anomaly_score"),
                    "detected_at": data.get("detected_at")
                }
            })

            try:
                index_anomaly(anomaly)
                print(f"✅ Anomaly {anomaly.anomaly_id} indexed")
            except Exception as e:
                print(f"⚠️ Failed to index anomaly: {e}")

            if data.get("is_anomaly") and confidence > 0.8:
                incident_type_id = get_incident_type_id(db, metric)
                severity_id = get_severity_id(db, value, confidence)
                service = (
                    db.query(Service)
                    .join(ServiceEndpoint, Service.service_id == ServiceEndpoint.service_id)
                    .filter(ServiceEndpoint.source_id == source_id)
                    .first()
                )

                if incident_type_id and severity_id and service:
                    incident = incident_repo.create({
                        "service_id": service.service_id,
                        "source_id": source_id,
                        "incident_type_id": incident_type_id,
                        "severity_level_id": severity_id,
                        "status_id": get_default_status_id(db),
                        "start_timestamp": ts,
                        "description": f"Auto-promoted from anomaly ({metric})",
                        "title": f"Anomaly in {metric}",
                        "escalation_level": "Level1"
                    })

                    anomaly.incident_id = incident.incident_id
                    anomaly.is_confirmed = True
                    db.commit()
                    db.refresh(anomaly)
                    print("🚨 Incident promoted and anomaly confirmed!")
                else:
                    print("⚠️ Could not promote incident (missing service or mappings).")

    except Exception as e:
        print("❌ ERROR:", str(e))
        time.sleep(5)
    finally:
        db.close()
