from sqlalchemy import func
from datetime import datetime
from app.db.models.prediction import Prediction
from app.db.models.rca_analysis import RCAAnalysis
from app.db.models.anomaly import Anomaly
from app.db.models.incident import Incident
from app.db.models.response_action import ResponseAction

def get_incident_predictor_data(db):
    completed = db.query(func.count()).filter(Prediction.status.in_(["Validated", "Invalid"])).scalar()
    queue = db.query(func.count()).filter(Prediction.status == "Pending").scalar()
    avg_conf = db.query(func.avg(Prediction.confidence_score)).filter(Prediction.status.in_(["Validated", "Invalid"])).scalar() or 0
    last_active = db.query(func.max(Prediction.prediction_timestamp)).scalar()
    return {
        "completed_tasks": completed,
        "queue": queue,
        "accuracy": round(avg_conf * 100, 2),
        "last_active": last_active.strftime("%Y-%m-%dT%H:%M:%S") if last_active else None
    }

def get_rca_agent_data(db):
    completed = db.query(func.count(RCAAnalysis.rca_id)).scalar()
    queue = 2  # Replace later with logic
    avg_conf = db.query(func.avg(RCAAnalysis.confidence_score)).scalar() or 0
    last_active = db.query(func.max(RCAAnalysis.analysis_timestamp)).scalar()
    return {
        "completed_tasks": completed,
        "queue": queue,
        "accuracy": round(avg_conf * 100, 2),
        "last_active": last_active.strftime("%Y-%m-%dT%H:%M:%S") if last_active else None
    }

def get_system_monitor_data(db):
    completed = db.query(func.count(Incident.incident_id)).scalar()
    queue = 3  # Estimate from open incidents
    return {
        "completed_tasks": completed,
        "queue": queue,
        "accuracy": 94,
        "last_active": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    }

def get_auto_remediation_data(db):
    completed = db.query(func.count()).filter(ResponseAction.status == "Completed").scalar()
    queue = db.query(func.count()).filter(ResponseAction.status.in_(["Pending", "In Progress"])).scalar()
    return {
        "completed_tasks": completed,
        "queue": queue,
        "accuracy": 96,
        "last_active": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    }

AGENT_REGISTRY = [
    {
        "name": "System Monitor",
        "version": "v2.1.3",
        "type": "monitoring",
        "status": "Active",
        "capabilities": ["Real-time monitoring", "Threshold detection", "Metric collection"],
        "data_loader": get_system_monitor_data
    },
    {
        "name": "Root Cause Analyzer",
        "version": "v1.8.1",
        "type": "analysis",
        "status": "Active",
        "capabilities": ["Log analysis", "Pattern recognition", "Correlation analysis"],
        "data_loader": get_rca_agent_data
    },
    {
        "name": "Incident Predictor",
        "version": "v3.2.0",
        "type": "prediction",
        "status": "Training",
        "capabilities": ["Forecasting", "Anomaly detection", "Early warnings"],
        "data_loader": get_incident_predictor_data
    },
    {
        "name": "Auto Remediation",
        "version": "v2.0.5",
        "type": "automation",
        "status": "Active",
        "capabilities": ["Script execution", "Playbook automation", "Runbook execution"],
        "data_loader": get_auto_remediation_data
    }
]
