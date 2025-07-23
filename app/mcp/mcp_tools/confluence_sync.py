import time
import json
import os
import traceback
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from atlassian import Confluence
from dotenv import load_dotenv

load_dotenv()

# === Load config from environment ===
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
CONFLUENCE_USER = os.getenv("CONFLUENCE_USER")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_SPACE = os.getenv("CONFLUENCE_SPACE_KEY")
CONFLUENCE_PAGE_TITLE = "PowerOps RCA Reports"

# === MCP folder to watch ===
MCP_STORE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp_store"))

# === Confluence client ===
confluence = Confluence(
    url=CONFLUENCE_URL,
    username=CONFLUENCE_USER,
    password=CONFLUENCE_API_TOKEN
)

class ConfluenceMCPHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory or not event.src_path.endswith(".json"):
            return

        # Retry reading the file up to 5 times
        for _ in range(5):
            try:
                with open(event.src_path, "r") as f:
                    mcp_data = json.load(f)
                break
            except (json.JSONDecodeError, IOError):
                time.sleep(0.5)
        else:
            print(f"❌ Could not read JSON file: {event.src_path}")
            return

        if mcp_data.get("type") == "rca_report":
            payload = mcp_data.get("payload", {})
            incident_id = payload.get("incident_id")
            service = payload.get("service", "Unknown")
            timestamp = payload.get("timestamp", "Unknown")
            root_cause = payload.get("root_cause", "N/A")
            recommendation = payload.get("recommendation", "N/A")
            generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            # === Format RCA block in Confluence storage-format HTML ===
            rca_block = f"""
<h2>🧠 RCA Report — Incident #{incident_id}</h2>

<table>
  <tr><th align="left">📍 Service</th><td>{service}</td></tr>
  <tr><th align="left">🕒 Timestamp</th><td>{timestamp}</td></tr>
  <tr><th align="left">🔍 Root Cause</th><td>{root_cause}</td></tr>
  <tr><th align="left">✅ Recommendation</th><td>{recommendation}</td></tr>
</table>

<p><strong>📁 Metadata:</strong></p>
<ul>
  <li><strong>Source:</strong> <code>rca_agent</code></li>
  <li><strong>Created via MCP:</strong> ✅</li>
  <li><strong>Logged at:</strong> {generated_at}</li>
</ul>

<hr/>
"""

            try:
                # Check if page exists
                existing_page = confluence.get_page_by_title(CONFLUENCE_SPACE, CONFLUENCE_PAGE_TITLE, expand="body.storage")

                if existing_page:
                    page_id = existing_page["id"]
                    old_body = existing_page["body"]["storage"]["value"]
                    new_body = rca_block + old_body  # Prepend newest report
                    confluence.update_page(
                        page_id=page_id,
                        title=CONFLUENCE_PAGE_TITLE,
                        body=new_body,
                        representation="storage"
                    )
                    print(f"✅ Appended RCA report to Confluence page: {CONFLUENCE_PAGE_TITLE}")
                else:
                    # Create new page
                    confluence.create_page(
                        space=CONFLUENCE_SPACE,
                        title=CONFLUENCE_PAGE_TITLE,
                        body=rca_block,
                        representation="storage"
                    )
                    print(f"✅ Created new Confluence page and added first RCA report.")
            except Exception as e:
                print(f"❌ Failed to update Confluence: {e}")
                traceback.print_exc()

def run_confluence_sync():
    observer = Observer()
    handler = ConfluenceMCPHandler()
    observer.schedule(handler, MCP_STORE, recursive=False)
    observer.start()
    print("📡 Confluence MCP Tool is running...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    run_confluence_sync()
