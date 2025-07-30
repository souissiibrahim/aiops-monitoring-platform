import os
import json
import requests  # ✅ For HTTP POST to MCP server
from datetime import datetime

from app.services.rca.smart_suggest_root_cause import suggest_root_cause
from app.utils.rca_formatter import generate_rca_markdown
from app.db.session import SessionLocal
from app.db.models.rca_report import RCAReport
from app.db.models.incident import Incident
from app.utils.slack_notifier import send_to_slack
from app.services.rca.update_faiss_index import append_to_faiss
from app.utils.jira_notifier import create_jira_ticket


def send_mcp_message_to_server(incident_id, service, root_cause, recommendation, timestamp):
    mcp_payload = {
        "type": "rca_report",
        "source": "rca_agent",
        "timestamp": timestamp,  # ✅ Add this line
        "payload": {
            "incident_id": incident_id,
            "service": service,
            "timestamp": timestamp,
            "root_cause": root_cause,
            "recommendation": recommendation
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
    return db.query(Incident).filter(~Incident.rca_reports.any()).all()


def save_markdown_report(incident_id: int, markdown: str):
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
            logs = [log.message for log in incident.log_entries]

            if not logs:
                print(f"⚠️ Skipping incident {incident.id}: no logs available.")
                continue

            print(f"🧠 Running RCA on incident {incident.id}...")
            result = suggest_root_cause(logs)

            rca_report = RCAReport(
                incident_id=incident.id,
                root_cause=result["root_cause"],
                recommendation=result["recommendation"],
                confidence=result["confidence"],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            db.add(rca_report)
            db.commit()
            print(f"✅ RCA report saved for incident {incident.id}.")
            append_to_faiss(logs, result["root_cause"], result["recommendation"])

            log_entry = incident.log_entries[0] if incident.log_entries else None
            service = log_entry.service if log_entry else "Unknown"
            timestamp = log_entry.timestamp.isoformat() if log_entry else datetime.utcnow().isoformat()

            markdown = generate_rca_markdown(
                incident_id=incident.id,
                service=service,
                timestamp=timestamp,
                logs=logs,
                root_cause=result["root_cause"],
                recommendation=result["recommendation"],
                confidence=result["confidence"]
            )

            save_markdown_report(incident.id, markdown)

            # ✅ Send Slack notification
            #try:
             #   send_to_slack(f"📢 New RCA Report for Incident `{incident.id}`:\n```{markdown}```")
              #  print(f"📨 Slack notification sent for incident {incident.id}.")
            #except Exception as slack_err:
             #   print(f"❌ Failed to send Slack message for incident {incident.id}: {slack_err}")

            # ✅ Create Jira Ticket
            #try:
             #   ticket_key = create_jira_ticket(
              #      summary=f"[Incident {incident.id}] RCA: {result['root_cause']}",
               #     description=markdown
               # )
               # print(f"🪪 Jira ticket {ticket_key} created for incident {incident.id}")
            #except Exception as jira_err:
              #  print(f"❌ Failed to create Jira ticket for incident {incident.id}: {jira_err}")

            # ✅ Send to MCP server
            send_mcp_message_to_server(
                incident_id=incident.id,
                service=service,
                root_cause=result["root_cause"],
                recommendation=result["recommendation"],
                timestamp=timestamp
            )

    except Exception as e:
        print(f"❌ RCA Agent Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    run_rca_agent()
