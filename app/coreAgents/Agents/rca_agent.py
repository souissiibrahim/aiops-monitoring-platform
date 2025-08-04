import os
import json
import requests
from datetime import datetime

from app.services.rca.smart_suggest_root_cause import suggest_root_cause
from app.utils.rca_formatter import generate_rca_markdown
from app.db.session import SessionLocal
from app.db.models.incident import Incident
from app.db.models.rca_analysis import RCAAnalysis
from app.db.models.telemetry_source import TelemetrySource
from app.utils.slack_notifier import send_to_slack
from app.services.rca.update_faiss_index import append_to_faiss


def send_mcp_message_to_server(incident_id, service, root_cause, recommendation, confidence, model, timestamp):
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
            "model": model
        }
    }

    print("📦 MCP Payload:")
    print(json.dumps(mcp_payload, indent=2))

    try:
        res = requests.post("http://localhost:8000/mcp/", json=mcp_payload)
        res.raise_for_status()
        print(f"📡 MCP message sent for incident {incident_id}: {res.json()}")
    except Exception as err:
        print(f"❌ Failed to send MCP message for incident {incident_id}: {err}")


def get_unprocessed_incidents(db):
    return db.query(Incident).filter(Incident.root_cause_id == None).all()


def save_markdown_report(incident_id: str, markdown: str):
    reports_dir = "rca_reports"
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, f"incident_{incident_id}_rca.md")
    with open(report_path, "w") as f:
        f.write(markdown)
    print(f"📝 Markdown RCA report saved: {report_path}")
    return report_path


def run_rca_agent():
    db = SessionLocal()
    try:
        incidents = get_unprocessed_incidents(db)
        print(f"🔎 Found {len(incidents)} incident(s) needing RCA.")

        for incident in incidents:
            source = db.query(TelemetrySource).filter_by(source_id=incident.source_id).first()
            service = incident.service.name if incident.service else "Unknown"
            incident_type = incident.incident_type.name if incident.incident_type else "Unknown"
            source_name = source.name if source else str(incident.source_id)

            # ⛏️ Simulated logs (replace with real logs from Loki later)
            logs = [
                "WARNING: Unexpected DNS response for api.internal.company.com — IP does not match known records",
                "ERROR: DNSSEC validation failed for multiple queries",
                "INFO: Switching to fallback DNS server due to suspected spoofing",
                "ALERT: Multiple conflicting A records returned for critical domain",
                "CRITICAL: Resolver flagged domain as potentially compromised — possible DNS cache poisoning"
            ]
            print(f"🧠 Running RCA on incident {incident.incident_id}...")

            result = suggest_root_cause(
                logs,
                incident_type=incident_type,
                metric_type="Network",
                service_name=service
            )

            # Sort by highest confidence
            sorted_recommendations = sorted(result["recommendations"], key=lambda r: r["confidence"], reverse=True)
            top_confidence = sorted_recommendations[0]["confidence"] if sorted_recommendations else 0.0

            rca = RCAAnalysis(
                incident_id=incident.incident_id,
                analysis_method=result.get("model", "Unknown"),
                root_cause_node_id=incident.source_id,
                confidence_score=top_confidence,
                contributing_factors={"logs_count": len(logs)},
                recommendations=sorted_recommendations,
                analysis_timestamp=datetime.utcnow(),
                analyst_team_id=None
            )

            db.add(rca)
            db.commit()
            db.refresh(rca)

            incident.root_cause_id = rca.rca_id
            db.commit()
            print(f"✅ RCAAnalysis saved and linked to incident {incident.incident_id}.")

            append_to_faiss(logs, result["root_cause"], sorted_recommendations[0]["text"])

            timestamp = datetime.utcnow().isoformat()

            markdown_recommendations = "\n".join(
                [f"- {r['text']} (confidence: {r['confidence']})" for r in sorted_recommendations]
            )

            markdown = generate_rca_markdown(
                incident_id=incident.incident_id,
                service=service,
                timestamp=timestamp,
                logs=logs,
                root_cause=result["root_cause"],
                recommendations=sorted_recommendations,
                confidence=top_confidence,
                model=result.get("model", "Unknown")
            )
            save_markdown_report(incident.incident_id, markdown)

            send_mcp_message_to_server(
                incident_id=incident.incident_id,
                service=service,
                root_cause=result["root_cause"],
                recommendation=markdown_recommendations,
                confidence=top_confidence,
                model=result.get("model", "Unknown"),
                timestamp=timestamp
            )

    except Exception as e:
        print(f"❌ RCA Agent Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    run_rca_agent()
