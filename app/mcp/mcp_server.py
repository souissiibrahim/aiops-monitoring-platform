import os
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal

# === Define MCP schema ===
class MCPMessage(BaseModel):
    type: Literal["incident", "rca_report", "resolution"]
    source: str
    payload: dict
    timestamp: str

# === Create MCP router ===
mcp_router = APIRouter()

# === Define storage path ===
MCP_STORAGE_DIR = os.path.join(os.path.dirname(__file__), "mcp_store")
os.makedirs(MCP_STORAGE_DIR, exist_ok=True)

# === Save incoming MCP message ===
@mcp_router.post("/", status_code=201)
async def receive_mcp_message(message: MCPMessage):
    try:
        # Extract incident_id from payload
        incident_id = message.payload.get("incident_id")
        if incident_id is None:
            raise HTTPException(status_code=400, detail="Missing 'incident_id' in payload.")

        # Create file name using incident ID and type
        filename = f"incident_{incident_id}_{message.type}.json"
        path = os.path.join(MCP_STORAGE_DIR, filename)

        # Write the MCP message to storage
        with open(path, "w") as f:
            json.dump(message.dict(), f, indent=2)

        return {"status": "ok", "file": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store MCP message: {e}")

@mcp_router.get("/", status_code=200)
async def list_mcp_messages():
    files = [f for f in os.listdir(MCP_STORAGE_DIR) if f.endswith(".json")]
    return {"stored_mcp_messages": files}
