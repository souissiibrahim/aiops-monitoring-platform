# app/utils/rca_formatter.py

from datetime import datetime
from typing import List, Dict, Union

def generate_rca_markdown(
    incident_id: Union[int, str],
    service: str,
    timestamp: str,
    logs: List[str],
    root_cause: str,
    recommendations: List[Dict[str, Union[str, float]]],
    confidence: float,
    model: str = "Unknown"
) -> str:
    """
    Generate a markdown-formatted RCA report with multiple recommendations.

    Parameters:
        - incident_id: ID of the incident
        - service: name of the service involved
        - timestamp: timestamp of the incident (string or datetime)
        - logs: list of log messages
        - root_cause: the identified root cause
        - recommendations: list of recommendation dicts with text and confidence
        - confidence: top confidence score
        - model: model name (LLM or FAISS)

    Returns:
        A markdown string.
    """

    # Format logs as bullet list
    formatted_logs = "\n".join([f"- {log}" for log in logs])

    # Format timestamp
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp)
        except Exception:
            timestamp = timestamp  # leave as-is

    # Format multiple recommendations
    formatted_recommendations = "\n".join([
        f"- {r['text']} (confidence: {r['confidence']})"
        for r in recommendations
    ])

    return f"""## 🛠️ RCA Report for Incident #{incident_id}

**Service:** `{service}`  
**Timestamp:** `{timestamp}`  
**Top Confidence:** `{confidence:.2f}`  
**Model Used:** `{model}`  
---

### 📋 Logs
{formatted_logs}

---

### 🧠 Root Cause
**{root_cause}**

---

### ✅ Recommendations
{formatted_recommendations}

---
"""
