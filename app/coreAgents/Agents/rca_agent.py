import os
import json
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from kafka import KafkaConsumer
from app.services.rca.smart_suggest_root_cause import suggest_root_cause
from app.utils.rca_formatter import generate_rca_markdown
from app.db.session import SessionLocal
from app.db.models.incident import Incident
from app.db.models.rca_analysis import RCAAnalysis
from app.db.models.telemetry_source import TelemetrySource  # kept if you later use it
from app.utils.slack_notifier import send_to_slack  # optional: used for ops signals
from app.services.rca.update_faiss_index import append_to_faiss

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------
MCP_URL = os.getenv("MCP_URL", "http://localhost:8000/mcp/")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")
LOGS_TOPIC = os.getenv("LOGS_TOPIC", "logs-cleaned")

# -------------------------------------------------------------------
# MCP helpers
# -------------------------------------------------------------------

def send_mcp_message_to_server(
    incident_id: str,
    service: str,
    root_cause: str,
    recommendation: str,
    confidence: float,
    model: str,
    timestamp: str,
) -> None:
    """Send the human-readable RCA report event to MCP (type=rca_report)."""
    mcp_payload = {
        "type": "rca_report",
        "source": "rca_agent",
        "timestamp": timestamp,
        "payload": {
            "incident_id": str(incident_id),
            "service": service,
            "timestamp": timestamp,
            "root_cause": root_cause,
            "recommendation": recommendation,
            "confidence": confidence,
            "model": model,
        },
    }

    try:
        res = requests.post(MCP_URL, json=mcp_payload, timeout=20)
        res.raise_for_status()
        print(f"📡 MCP rca_report sent for incident {incident_id}: {res.json()}")
    except Exception as err:
        print(f"❌ Failed to send MCP rca_report for incident {incident_id}: {err}")


def send_mcp_remediation_request(
    *,
    incident_id: str,
    service: str,
    incident_type_id: Optional[str],
    root_cause: Optional[str],
    top_rec_text: str,
    top_rec_conf: float,
) -> None:
    """Send the remediation request; selector will use incident_type_id deterministically."""
    payload = {
        "type": "remediation_request",
        "source": "rca_agent",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "payload": {
            "incident_id": str(incident_id),
            "service": service,
            "incident_type_id": incident_type_id,   # <-- ID is what the selector needs
            "root_cause": root_cause,
            "recommendation_text": top_rec_text,
            "recommendation_confidence": float(top_rec_conf),
        },
    }
    try:
        res = requests.post(MCP_URL, json=payload, timeout=20)
        res.raise_for_status()
        print(f"🤝 MCP remediation_request sent. Result: {res.json()}")
    except Exception as err:
        print(f"❌ Failed to send remediation_request: {err}")

# -------------------------------------------------------------------
# DB helpers
# -------------------------------------------------------------------

def get_unprocessed_incidents(db) -> List[Incident]:
    """Incidents that have no RCA yet."""
    return db.query(Incident).filter(Incident.root_cause_id == None).all()  # noqa: E711


def save_markdown_report(incident_id: str, markdown: str) -> str:
    reports_dir = "rca_reports"
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, f"incident_{incident_id}_rca.md")
    with open(report_path, "w") as f:
        f.write(markdown)
    print(f"📝 Markdown RCA report saved: {report_path}")
    return report_path

# -------------------------------------------------------------------
# Logs fetcher (Kafka)
# -------------------------------------------------------------------

def fetch_logs_for_incident_by_service(
    service_name: str,
    incident_start_time: datetime,
    topic: str = LOGS_TOPIC,
    bootstrap_servers: str = KAFKA_BOOTSTRAP,
) -> List[str]:
    print(f"🛰️ Fetching logs for '{service_name}' near {incident_start_time}...")
    logs: List[str] = []

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        group_id=None,                  # stateless scan
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=3000,
    )

    # Ensure incident timestamp is timezone-aware (UTC)
    incident_ts = incident_start_time.replace(tzinfo=timezone.utc)
    start_window = incident_ts - timedelta(minutes=2)
    end_window = incident_ts + timedelta(minutes=3)
    deadline = datetime.utcnow().timestamp() + 5  # max 5 seconds to scan

    try:
        for msg in consumer:
            try:
                entry = json.loads(msg.value.decode("utf-8"))
            except Exception as e:
                print(f"⚠️ Skipping bad Kafka message: {e}")
                continue

            if entry.get("service_name") != service_name:
                continue

            try:
                log_ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            except Exception as e:
                print(f"⚠️ Invalid log timestamp format: {e}")
                continue

            if start_window <= log_ts <= end_window:
                logs.append(entry.get("message", ""))

            if datetime.utcnow().timestamp() > deadline:
                break
    finally:
        consumer.close()

    print(f"📄 Retrieved {len(logs)} logs.")
    for i, log in enumerate(logs[:10], 1):  # cap stdout noise
        print(f"🧾 Log {i}: {log}")
    return logs if logs else ["INFO: No logs found."]


def run_rca_agent() -> None:
    db = SessionLocal()
    try:
        incidents = get_unprocessed_incidents(db)
        print(f"🔎 Found {len(incidents)} incident(s) needing RCA.")

        for incident in incidents:
            # Basic context
            service_name = incident.service.name if getattr(incident, "service", None) else "Unknown"
            incident_type_name = (
                incident.incident_type.name if getattr(incident, "incident_type", None) else "Unknown"
            )
            incident_type_id = str(incident.incident_type_id) if incident.incident_type_id else None

            # Fetch logs near the incident time window
            logs = fetch_logs_for_incident_by_service(service_name, incident.start_timestamp)

            print(f"🧠 Running RCA on incident {incident.incident_id} (type={incident_type_name})...")
            # Call your RCA engine (FAISS-known or Groq-unknown under the hood)
            rca_result: Dict[str, Any] = suggest_root_cause(
                logs,
                incident_type=incident_type_name,
                metric_type="Generic",
                service_name=service_name,
            )

            # Recommendations (robust guard for missing/empty)
            recs: List[Dict[str, Any]] = rca_result.get("recommendations") or []
            recs_sorted = sorted(recs, key=lambda r: r.get("confidence", 0.0), reverse=True)
            top_text: str = recs_sorted[0]["text"] if recs_sorted else ""
            top_conf: float = float(recs_sorted[0].get("confidence", 0.0)) if recs_sorted else 0.0

            # Persist RCA to DB
            rca = RCAAnalysis(
                incident_id=incident.incident_id,
                analysis_method=rca_result.get("model", "Unknown"),
                root_cause_node_id=incident.source_id,
                confidence_score=top_conf,
                contributing_factors={"logs_count": len(logs)},
                recommendations=recs_sorted,
                analysis_timestamp=datetime.utcnow(),
                analyst_team_id=None,
            )
            db.add(rca)
            db.commit()
            db.refresh(rca)

            # Link incident to RCA
            incident.root_cause_id = rca.rca_id
            db.add(incident)
            db.commit()
            print(f"✅ RCAAnalysis saved and linked to incident {incident.incident_id}.")

            # Update FAISS memory if we have good artifacts
            root_cause_text = rca_result.get("root_cause")
            if root_cause_text and top_text:
                try:
                    append_to_faiss(logs, root_cause_text, top_text)
                except Exception as e:
                    print(f"⚠️ append_to_faiss failed: {e}")

            # Build a concise Markdown report
            ts_iso = datetime.utcnow().isoformat() + "Z"
            md_recs_lines = [f"- {r.get('text','')} (confidence: {r.get('confidence',0.0)})" for r in recs_sorted]
            md_recs = "\n".join(md_recs_lines)

            markdown = generate_rca_markdown(
                incident_id=incident.incident_id,
                service=service_name,
                timestamp=ts_iso,
                logs=logs,
                root_cause=root_cause_text or "Unknown",
                recommendations=recs_sorted,
                confidence=top_conf,
                model=rca_result.get("model", "Unknown"),
            )
            save_markdown_report(str(incident.incident_id), markdown)

            # Send RCA report to MCP (for traceability)
            send_mcp_message_to_server(
                incident_id=str(incident.incident_id),
                service=service_name,
                root_cause=root_cause_text or "Unknown",
                recommendation=md_recs,
                confidence=top_conf,
                model=rca_result.get("model", "Unknown"),
                timestamp=ts_iso,
            )

            # Finally: request remediation (auto/human decided by selector thresholds)
            if not top_text:
                print("ℹ️ No recommendation text found; skipping remediation request.")
                continue

            if not incident_type_id:
                print("ℹ️ Incident has no incident_type_id; skipping remediation request.")
                continue

            send_mcp_remediation_request(
                incident_id=str(incident.incident_id),
                service=service_name,
                incident_type_id=incident_type_id,   # <-- deterministic selector filter
                root_cause=root_cause_text,
                top_rec_text=top_text,
                top_rec_conf=top_conf,
            )

    except Exception as e:
        print(f"❌ RCA Agent Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    run_rca_agent()
