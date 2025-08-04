# app/v1/endpoints/agent_endpoints.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.agent_registry import AGENT_REGISTRY
from app.utils.response import success_response

router = APIRouter()


@router.get("/agents/status")
def get_all_agents_status(db: Session = Depends(get_db)):
    agents_data = []

    for agent in AGENT_REGISTRY:
       
        data = agent["data_loader"](db)

        
        agents_data.append({
            "name": agent["name"],
            "version": agent["version"],
            "type": agent["type"],
            "status": agent["status"],
            "capabilities": agent["capabilities"],
            **data
        })

    total_agents = len(agents_data)
    avg_accuracy = round(sum(agent["accuracy"] for agent in agents_data) / total_agents, 2)
    total_queue = sum(agent["queue"] for agent in agents_data)

    return success_response({
        "total_active_agents": total_agents,
        "avg_accuracy": avg_accuracy,
        "tasks_in_queue": total_queue,
        "agents": agents_data
    }, "Agent dashboard data fetched successfully.")
