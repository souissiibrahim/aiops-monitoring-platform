# scripts/anomaly_kafka_ingester.py
import os
import json
import time
from datetime import datetime, timezone
from uuid import UUID
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
from app.db.models.incident_status import IncidentStatus
from app.services.elasticsearch.anomaly_service import index_anomaly
from app.monitor.heartbeat import start_heartbeat

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------
hb = start_heartbeat("scripts/anomaly_kafka_ingester.py", interval_s=30, version="dev")

KAFKA_TOPIC = os.getenv("KAFKA_ANOMALY_TOPIC", "anomalies")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")
LINK_WINDOW_SEC = int(os.getenv("LINK_WINDOW_SEC", "600"))  # ±10 min

# Require anomalies to be this recent (by event timestamp) to be ingested
INGEST_MAX_EVENT_AGE_SEC = int(os.getenv("INGEST_MAX_EVENT_AGE_SEC", "180"))

# Promotion gate
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", "0.8"))

# Path to JSON mapping file (metric_name -> incident_type_name)
MAPPING_FILE = os.getenv("INCIDENT_MAPPING_FILE", "scripts/incident_mapping.json")

# ---------------------------------------------------------------------
# Load mapping (JSON)
# Keys are normalized to lowercase for robust matching
# ---------------------------------------------------------------------
def load_incident_map(file_path: str) -> dict:
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
        normalized = {str(k).strip().lower(): str(v).strip() for k, v in data.items()}
        if not normalized:
            print(f"⚠️ Loaded empty incident mapping from {file_path}")
        else:
            print(f"✅ Loaded incident mapping ({len(normalized)} entries) from {file_path}")
        return normalized
    except FileNotFoundError:
        print(f"⚠️ Mapping file not found: {file_path}. Using empty mapping.")
        return {}
    except Exception as e:
        print(f"⚠️ Failed to load incident mapping ({file_path}): {e}. Using empty mapping.")
        return {}

INCIDENT_MAP = load_incident_map(MAPPING_FILE)

# ---------------------------------------------------------------------
# Kafka consumer
# ---------------------------------------------------------------------
consumer = KafkaConsumer(
    KAFKA_TOPIC,
    bootstrap_servers=KAFKA_BOOTSTRAP,
    group_id="anomaly-ingester",
    auto_offset_reset="latest",
    enable_auto_commit=True,
    value_deserializer=lambda m: m.decode("utf-8"),
)

print("🚀 Anomaly Kafka ingester (JSON rule-based) running...")

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def get_default_status_id(db: Session) -> UUID | None:
    status = db.query(IncidentStatus).filter_by(name="Open").first()
    return status.status_id if status else None

def get_severity_id(db: Session, value: float, confidence: float) -> UUID | None:
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

def get_or_create_incident_type(db: Session, name: str, description: str, category: str) -> UUID | None:
    existing = db.query(IncidentType).filter_by(name=name).first()
    if existing:
        return existing.incident_type_id
    new_type = IncidentType(name=name, description=description, category=category)
    db.add(new_type)
    db.commit()
    db.refresh(new_type)
    print(f"🆕 Created new IncidentType: {name}")
    return new_type.incident_type_id

def get_source_by_instance(db: Session, instance: str) -> TelemetrySource | None:
    return db.query(TelemetrySource).filter(TelemetrySource.name == instance).first()

def to_utc_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")

def predict_incident_type_name(data: dict) -> str:
    """
    Rule-based classifier using external JSON mapping.
    - Exact lowercase match first
    - Then substring fallback (helps when metric names include extra suffixes/labels)
    """
    raw_metric = (data.get("metric_name") or "").strip()
    metric = raw_metric.lower()
    if metric in INCIDENT_MAP:
        return INCIDENT_MAP[metric]
    for k, v in INCIDENT_MAP.items():
        if k in metric:
            return v
    return "Unknown"

def parse_event_ts(ts_val):
    """Return float epoch seconds from a number or ISO string; None on failure."""
    if isinstance(ts_val, (int, float)):
        return float(ts_val)
    if isinstance(ts_val, str):
        try:
            return datetime.fromisoformat(ts_val.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None
    return None

# ---------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------
while True:
    db: Session = SessionLocal()
    repo = AnomalyRepository(db, None)
    incident_repo = IncidentRepository(db, None)
    pred_repo = PredictionRepository(db, None)
    try:
        for msg in consumer:
            # Parse message
            try:
                data = json.loads(msg.value)
            except Exception as e:
                print(f"❌ Invalid JSON: {e} | Raw: {msg}")
                continue

            metric = data.get("metric_name")
            instance = data.get("instance")

            # Resolve event timestamp & recency gate (ignore old anomalies)
            event_ts = parse_event_ts(data.get("timestamp"))
            if event_ts is None:
                print("⚠️ Missing/invalid 'timestamp' → skipping.")
                continue

            now = time.time()
            age = now - event_ts
            if age > INGEST_MAX_EVENT_AGE_SEC:
                print(f"ℹ️ Skipping old event (age={age:.1f}s > {INGEST_MAX_EVENT_AGE_SEC}s): {metric}")
                continue

            # Confidence & promotion gate: ONLY proceed for emitted anomalies with sufficient confidence
            confidence = float(data.get("confidence", data.get("data_quality", 0.0)))
            if not (data.get("is_anomaly") and confidence > CONF_THRESHOLD):
                print("ℹ️ Not an emitted anomaly or low confidence → not stored/indexed.")
                continue

            # Basic field checks
            try:
                value = float(data["value"])
                ts = datetime.fromtimestamp(float(event_ts), tz=timezone.utc)
            except Exception as e:
                print(f"❌ Invalid data format: {e}")
                continue

            if not instance:
                print("⚠️ No 'instance' in anomaly.")
                continue

            source = get_source_by_instance(db, instance)
            if not source:
                print(f"❌ No TelemetrySource found for instance '{instance}'")
                continue

            # Dedup (against truly emitted anomalies only)
            exists = db.query(Anomaly).filter_by(
                source_id=source.source_id,
                metric_type=metric,
                timestamp=ts,
                value=value,
            ).first()
            if exists:
                print("⚠️ Duplicate emitted anomaly → skipped.")
                continue

            # At this point we STORE and INDEX (emitted anomaly only)
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
                    "anomaly_score_rel": data.get("anomaly_score_rel"),
                    "detected_at": data.get("detected_at"),
                    "instance": instance,
                },
            })

            # Index to Elasticsearch (emitted anomalies only)
            try:
                index_anomaly(anomaly)
                print(f"✅ Indexed emitted anomaly {anomaly.anomaly_id}")
            except Exception as e:
                print(f"⚠️ Failed to index anomaly: {e}")

            # Promote to incident
            itype_name = predict_incident_type_name(data)
            if itype_name == "Unknown":
                print(f"ℹ️ Unknown mapping for metric '{metric}'. Skipping incident promotion.")
                continue

            incident_type_id = get_or_create_incident_type(
                db,
                name=itype_name,
                description=f"Predicted from anomaly: {metric}",
                category="Performance",  # adjust if you want category-specific
            )
            severity_id = get_severity_id(db, value, confidence)

            # Service lookup via endpoint/source relationship
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
                    "escalation_level": "Level1",
                })

                anomaly.incident_id = incident.incident_id
                anomaly.is_confirmed = True
                db.commit()
                db.refresh(anomaly)
                print("🚨 Incident promoted and anomaly confirmed!")

                # Optional: link to nearest pending prediction
                try:
                    itype_name_db = db.query(IncidentType).filter(
                        IncidentType.incident_type_id == incident_type_id
                    ).first().name
                    severity_name = get_severity_name(db, severity_id) or "High"
                    instance_name = source.name
                    start_ts_iso = to_utc_z(ts)

                    linked_pid = pred_repo.link_nearest_pending(
                        incident_id=incident.incident_id,
                        instance=instance_name,
                        incident_type=itype_name_db,
                        severity=severity_name,
                        start_ts_utc_iso=start_ts_iso,
                        window_sec=LINK_WINDOW_SEC,
                    )
                    if linked_pid:
                        print(f"🔗 Linked prediction {linked_pid} → incident {incident.incident_id}")
                    else:
                        print(f"🔎 No Pending prediction within ±{LINK_WINDOW_SEC}s for incident {incident.incident_id}")
                except AttributeError as e:
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
