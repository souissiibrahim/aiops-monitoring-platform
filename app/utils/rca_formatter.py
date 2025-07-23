# app/utils/rca_formatter.py

from datetime import datetime

def generate_rca_markdown(incident_id: int, service: str, timestamp: str, logs: list[str], root_cause: str, recommendation: str, confidence: float) -> str:
    """
    Generate a markdown-formatted RCA report.
    
    Parameters:
        - incident_id: ID of the incident
        - service: name of the service involved
        - timestamp: timestamp of the incident (string or datetime)
        - logs: list of log messages
        - root_cause: the identified root cause
        - recommendation: suggested fix
        - confidence: confidence score from LLM or FAISS

    Returns:
        A string containing the markdown-formatted report.
    """

    # Format logs as bullet list
    formatted_logs = "\n".join([f"- {log}" for log in logs])

    # Format timestamp
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp)
        except Exception:
            timestamp = timestamp  # keep it as-is if not ISO format

    return f"""## 🛠️ RCA Report for Incident #{incident_id}

**Service:** `{service}`  
**Timestamp:** `{timestamp}`  
**Confidence:** `{confidence:.2f}`

---

### 📋 Logs
{formatted_logs}

---

### 🧠 Root Cause
**{root_cause}**

---

### ✅ Recommendation
**{recommendation}**

---
"""

