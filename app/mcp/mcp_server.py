import os
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal

# NEW: import the remediation graph runner
from app.langchain.graphs.remediation_graph import run_remediation_graph

class MCPMessage(BaseModel):
    type: Literal["incident", "rca_report", "resolution", "remediation_request"]
    source: str
    payload: dict
    timestamp: str

mcp_router = APIRouter()

MCP_STORAGE_DIR = os.path.join(os.path.dirname(__file__), "mcp_store")
os.makedirs(MCP_STORAGE_DIR, exist_ok=True)

@mcp_router.post("/", status_code=201)
async def receive_mcp_message(message: MCPMessage):
    try:
        incident_id = message.payload.get("incident_id")
        if incident_id is None:
            raise HTTPException(status_code=400, detail="Missing 'incident_id' in payload.")

        # Always store the inbound message (your current behavior)
        filename = f"incident_{incident_id}_{message.type}.json"
        path = os.path.join(MCP_STORAGE_DIR, filename)
        with open(path, "w") as f:
            json.dump(message.dict(), f, indent=2)

        # If this is a remediation request, run the LangGraph remediation pipeline
        result = None
        if message.type == "remediation_request":
            try:
                result = run_remediation_graph({
                    "incident_id": str(incident_id),
                    "service": message.payload.get("service"),
                    "incident_type_id": message.payload.get("incident_type_id"), 
                    "root_cause": message.payload.get("root_cause"),
                    "recommendation_text": message.payload.get("recommendation_text", ""),
                    "recommendation_confidence": float(message.payload.get("recommendation_confidence", 0.0)),
                })
                # Also store the result for traceability
                out_file = f"incident_{incident_id}_remediation_result.json"
                out_path = os.path.join(MCP_STORAGE_DIR, out_file)
                with open(out_path, "w") as f:
                    json.dump(result, f, indent=2)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Remediation flow failed: {e}")

        return {"status": "ok", "file": filename, "result": result}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process MCP message: {e}")

@mcp_router.get("/", status_code=200)
async def list_mcp_messages():
    files = [f for f in os.listdir(MCP_STORAGE_DIR) if f.endswith(".json")]
    return {"stored_mcp_messages": files}
