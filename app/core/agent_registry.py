from sqlalchemy import func, cast, Float
from datetime import datetime

from app.db.models.prediction import Prediction
from app.db.models.rca_analysis import RCAAnalysis
from app.db.models.incident import Incident
from app.db.models.response_action import ResponseAction
from app.db.models.model import Model  # if you use model accuracies

def pct_from_maybe_unit(x):
    if x is None:
        return 0.0
    return max(0.0, min(100.0, x if x > 1.0 else x * 100.0))

def _to_int(x):
    try:
        return int(x or 0)
    except Exception:
        return 0

# ---- Incident Predictor helpers ----
PRED_COMPLETED_STATUSES = ["Validated", "Invalid", "Expired"]

def _avg_accuracy_of_models(db, model_names):
    acc_as_float = cast(func.nullif(Model.accuracy, ''), Float)
    avg_q = db.query(func.avg(acc_as_float)).filter(
        Model.is_deleted == False,
        Model.name.in_(model_names),
        acc_as_float > 0
    )
    avg_accuracy = avg_q.scalar()
    return round(float(avg_accuracy) if avg_accuracy is not None else 0.0, 2)

def get_incident_predictor_data(db):
    completed = db.query(func.count()).select_from(Prediction).filter(
        Prediction.status.in_(PRED_COMPLETED_STATUSES)
    ).scalar()

    queue = db.query(func.count()).select_from(Prediction).filter(
        Prediction.status == "Pending"
    ).scalar()

    predictor_models = ["prophet-memory", "prophet-disk", "prophet-cpu"]
    avg_models_acc = _avg_accuracy_of_models(db, predictor_models)

    last_active = db.query(func.max(Prediction.prediction_timestamp)).scalar()

    return {
        "completed_tasks": _to_int(completed),
        "queue": _to_int(queue),
        "accuracy": avg_models_acc,
        "last_active": last_active.strftime("%Y-%m-%dT%H:%M:%S") if last_active else None
    }

def get_rca_agent_data(db):
    completed = db.query(func.count()).select_from(RCAAnalysis).scalar()

    queue = db.query(func.count(Incident.incident_id)).filter(
        ~db.query(RCAAnalysis)
         .filter(RCAAnalysis.incident_id == Incident.incident_id)
         .exists()
    ).scalar()

    avg_conf = db.query(func.avg(RCAAnalysis.confidence_score)).scalar()
    last_active = db.query(func.max(RCAAnalysis.analysis_timestamp)).scalar()

    return {
        "completed_tasks": _to_int(completed),
        "queue": _to_int(queue),
        "accuracy": round(pct_from_maybe_unit(avg_conf), 2),
        "last_active": last_active.strftime("%Y-%m-%dT%H:%M:%S") if last_active else None
    }

def get_system_monitor_data(db):
    completed = db.query(func.count()).select_from(Incident).scalar()
    queue = 0
    return {
        "completed_tasks": _to_int(completed),
        "queue": queue,
        "accuracy": 0,
        "last_active": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    }

def get_auto_remediation_data(db):
    completed = db.query(func.count()).select_from(ResponseAction).filter(
        ResponseAction.status == "Completed"
    ).scalar()

    queue = db.query(func.count()).select_from(ResponseAction).filter(
        ResponseAction.status.in_(["Pending", "In Progress"])
    ).scalar()

    return {
        "completed_tasks": _to_int(completed),
        "queue": _to_int(queue),
        "accuracy": 100,
        "last_active": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    }

AGENT_REGISTRY = [
    {
        "name": "System Monitor",
        "version": "v1",
        "type": "monitoring",
        "status": "Active",
        "capabilities": [
            "Real-time monitoring",
            "Threshold detection",
            "Metric collection",
            "Anomaly detection"
        ],
        "data_loader": get_system_monitor_data
    },
    {
        "name": "Root Cause Analyzer",
        "version": "v1",
        "type": "analysis",
        "status": "Active",
        "capabilities": ["Log analysis", "Pattern recognition", "Correlation analysis"],
        "data_loader": get_rca_agent_data
    },
    {
        "name": "Incident Predictor",
        "version": "v1",
        "type": "prediction",
        "status": "Training",
        "capabilities": ["Forecasting", "Anomaly detection", "Early warnings"],
        "data_loader": get_incident_predictor_data
    },
    {
        "name": "Auto Remediation",
        "version": "v1",
        "type": "automation",
        "status": "Active",
        "capabilities": ["Script execution", "Playbook automation", "Runbook execution"],
        "data_loader": get_auto_remediation_data
    }
]
