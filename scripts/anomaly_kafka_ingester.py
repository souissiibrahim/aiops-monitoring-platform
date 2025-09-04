import json
import time
import joblib
import pandas as pd
from datetime import datetime, timezone
from uuid import UUID, uuid4
from kafka import KafkaConsumer
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.repositories.anomaly_repository import AnomalyRepository
from app.db.repositories.incident_repository import IncidentRepository
from app.db.repositories.prediction_repository import PredictionRepository

from app.db.models.anomaly import Anomaly
from app.db.models.incident import Incident
from app.db.models.telemetry_source import TelemetrySource
from app.db.models.service import Service
from app.db.models.incident_type import IncidentType
from app.db.models.severity_level import SeverityLevel
from app.db.models.service_endpoint import ServiceEndpoint
from app.services.elasticsearch.anomaly_service import index_anomaly
from app.db.models.incident_status import IncidentStatus
from app.monitor.heartbeat import start_heartbeat


hb = start_heartbeat("scripts/anomaly_kafka_ingester.py", interval_s=30, version="dev")
model = joblib.load("scripts/incident_type_classifier.pkl")
label_encoder = joblib.load("scripts/incident_type_label_encoder.pkl")
feature_columns = joblib.load("scripts/incident_type_feature_columns.pkl")

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

def get_severity_name(db: Session, severity_id: UUID) -> str | None:
    lvl = db.query(SeverityLevel).filter(SeverityLevel.severity_level_id == severity_id).first()
    return lvl.name if lvl else None

def map_metric_to_known(metric: str, known_metrics: list) -> str:
    for known in known_metrics:
        if known in metric:
            return known
    return "unknown"

def prepare_features(data: dict) -> pd.DataFrame:
    metric = data.get("metric_name", "")
    known_metrics = [col.replace("metric_name_", "") for col in feature_columns if col.startswith("metric_name_")]
    mapped_metric = map_metric_to_known(metric, known_metrics)

    df = pd.DataFrame([{
        "metric_name": data.get("metric_name", ""),
        "value": data.get("value", 0.0),
        "confidence": data.get("confidence", 0.0),
        "anomaly_score": data.get("anomaly_score", 0.0)
    }])
    df = pd.get_dummies(df, columns=["metric_name"])
    #df = df.reindex(columns=model.get_booster().feature_names, fill_value=0)
    df = df.reindex(columns=feature_columns, fill_value=0)
    return df

def predict_incident_type_name(data: dict) -> str:
    X = prepare_features(data)
    encoded = model.predict(X)[0]
    return label_encoder.inverse_transform([int(encoded)])[0]

def get_or_create_incident_type(db: Session, name: str, description: str, category: str) -> UUID:
    existing = db.query(IncidentType).filter_by(name=name).first()
    if existing:
        return existing.incident_type_id
    new_type = IncidentType(
        name=name,
        description=description,
        category=category
    )
    db.add(new_type)
    db.commit()
    db.refresh(new_type)
    print(f"🆕 Created new IncidentType: {name}")
    return new_type.incident_type_id

def get_source_by_instance(db: Session, instance: str) -> TelemetrySource:
    return db.query(TelemetrySource).filter(TelemetrySource.name == instance).first()

def to_utc_z(dt: datetime) -> str:
    """Return ISO timestamp in UTC with trailing 'Z'."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")

while True:
    db: Session = SessionLocal()
    repo = AnomalyRepository(db, None)
    incident_repo = IncidentRepository(db, None)
    pred_repo = PredictionRepository(db, None)
    try:
        for msg in consumer:
            try:
                data = json.loads(msg.value)
            except Exception as e:
                print(f"❌ Invalid JSON: {e} | Raw: {msg}")
                continue

            print("📅 Received::", data)

            metric = data.get("metric_name")
            instance = data.get("instance", None)
            try:
                value = float(data["value"])
                confidence = float(data.get("confidence", 1.0))
                #ts = datetime.utcfromtimestamp(float(data["timestamp"]))
                ts = datetime.fromtimestamp(float(data["timestamp"]), tz=timezone.utc)
            except Exception as e:
                print(f"❌ Invalid data format: {e}")
                continue

            if not instance:
                print("⚠️ No instance field found in anomaly.")
                continue

            source = get_source_by_instance(db, instance)
            if not source:
                print(f"❌ No source found for instance '{instance}'")
                continue

            exists = db.query(Anomaly).filter_by(
                source_id=source.source_id,
                metric_type=metric,
                timestamp=ts,
                value=value
            ).first()
            if exists:
                print("⚠️ Duplicate anomaly.")
                continue

            anomaly = repo.create({
                "source_id": source.source_id,
                "metric_type": metric,
                "value": value,
                "confidence_score": confidence,
                "timestamp": ts,
                "detection_method": "AutoEncoder",
                "anomaly_metadata": {
                    "collection_delay": data.get("collection_delay"),
                    "anomaly_score": data.get("anomaly_score"),
                    "detected_at": data.get("detected_at"),
                    "instance": instance
                }
            })

            try:
                index_anomaly(anomaly)
                print(f"✅ Anomaly {anomaly.anomaly_id} indexed")
            except Exception as e:
                print(f"⚠️ Failed to index anomaly: {e}")

            if data.get("is_anomaly") and confidence > 0.8:
                incident_type_name = predict_incident_type_name(data)
                incident_type_id = get_or_create_incident_type(
                    db,
                    name=incident_type_name,
                    description=f"Predicted from anomaly: {metric}",
                    category="Performance"
                )
                severity_id = get_severity_id(db, value, confidence)

                service = (
                    db.query(Service)
                    .join(ServiceEndpoint, Service.service_id == ServiceEndpoint.service_id)
                    .filter(ServiceEndpoint.source_id == source.source_id)
                    .first()
                )

                if incident_type_id and severity_id and service:
                    incident = incident_repo.create({
                        "service_id": service.service_id,
                        "source_id": source.source_id,
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
                    try:
                        # Resolve human-readable names for linking
                        itype_name = db.query(IncidentType).filter(
                            IncidentType.incident_type_id == incident_type_id
                        ).first().name
                        severity_name = get_severity_name(db, severity_id) or "High"
                        instance_name = source.name
                        start_ts_iso = to_utc_z(ts)

                        linked_pid = pred_repo.link_nearest_pending(
                            incident_id=incident.incident_id,
                            instance=instance_name,
                            incident_type=itype_name,
                            severity=severity_name,
                            start_ts_utc_iso=start_ts_iso,
                            window_sec=LINK_WINDOW_SEC,
                        )
                        if linked_pid:
                            print(f"🔗 Linked prediction {linked_pid} → incident {incident.incident_id}")
                        else:
                            print(f"🔎 No Pending prediction within ±{LINK_WINDOW_SEC}s for incident {incident.incident_id}")

                    except AttributeError as e:
                        # If the repository doesn't have link_nearest_pending yet
                        print(f"ℹ️ Skipping prediction linking (method missing?): {e}")
                    except Exception as e:
                        print(f"⚠️ Prediction linking failed: {e}")

                else:
                    print("⚠️ Could not promote incident (missing service or mappings).")

    except Exception as e:
        print("❌ ERROR:", str(e))
        time.sleep(5)
    finally:
        db.close()
