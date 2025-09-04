from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from app.db.session import get_db
from app.db.models.prediction import Prediction
from app.db.models.telemetry_source import TelemetrySource 
from app.services.prometheus.client import (
    current_cpu_pct, current_mem_pct, current_disk_pct,
    current_network_mbps, current_network_util_pct,
    uptime_seconds,  
)

router = APIRouter()


CPU_METRIC  = "node_cpu_utilization"
MEM_METRIC  = "node_memory_utilization"
DISK_METRIC = "node_filesystem_usage"

LABELS = {
    CPU_METRIC:  "CPU Usage",
    MEM_METRIC:  "Memory Usage",
    DISK_METRIC: "Disk Space",
}

def _current_pct(metric: str, instance: str, mountpoint: str = "/") -> float:
    """Get current usage from Prometheus (CPU, Memory, Disk)."""
    try:
        if metric == CPU_METRIC:
            return current_cpu_pct(instance)
        if metric == MEM_METRIC:
            return current_mem_pct(instance)
        return current_disk_pct(instance, mountpoint)
    except Exception:
        return 0.0

def _normalize_conf_pct(val) -> float:
    """Ensure confidence is always expressed as a percentage 0–100."""
    if val is None:
        return 0.0
    try:
        x = float(val)
    except Exception:
        return 0.0
    return max(0.0, min(100.0, x if x > 1.0 else x * 100.0))

def _latest_prediction(db: Session, metric: str, instance: str, include_expired: bool):
    """Fetch the latest prediction for this metric+instance."""
    q = (
        db.query(Prediction)
        .filter(
            Prediction.input_features["metric_name"].astext == metric,
            Prediction.input_features["instance"].astext == instance,
        )
        .order_by(desc(Prediction.prediction_timestamp))
    )
    if not include_expired:
        q = q.filter(Prediction.status != "Expired")
    return q.first()

def _build_card(db: Session, metric: str, instance: str, include_expired: bool, mountpoint: str = "/") -> dict | None:
    """Build a card payload. Return None if no prediction exists."""
    pred = _latest_prediction(db, metric, instance, include_expired)
    if not pred:
        return None

    current = _current_pct(metric, instance, mountpoint)

    yhat = None
    conf = None
    severity = None
    incident_type = None
    threshold = None
    forecast_for = None

    if pred.prediction_output:
        yhat = pred.prediction_output.get("yhat")
        conf = pred.prediction_output.get("confidence", pred.confidence_score)
        severity = pred.prediction_output.get("severity_name")
        incident_type = pred.prediction_output.get("incident_type_name")

    if conf is None:
        conf = pred.confidence_score

    if pred.input_features:
        threshold = pred.input_features.get("threshold")
        forecast_for = pred.input_features.get("forecast_for")

    pt = pred.prediction_timestamp
    if pt.tzinfo is None:
        pt = pt.replace(tzinfo=timezone.utc)
    is_fresh = (datetime.now(timezone.utc) - pt) <= timedelta(hours=48)

    return {
        "title": LABELS.get(metric, metric),
        "metric": metric,
        "instance": instance,
        "current_pct": round(current, 2),

        "predicted_usage": round(float(yhat) * 100.0, 2) if yhat is not None else None,
        "confidence_pct": round(_normalize_conf_pct(conf), 2),
        "severity": severity,
        "incident_type": incident_type,
        "threshold": threshold,
        "status": pred.status,

        "prediction_timestamp": pred.prediction_timestamp.isoformat(),
        "forecast_for": forecast_for,
        "is_fresh": is_fresh,
    }

@router.get("/current", tags=["performance"])
def current_usage(
    instance: str = Query(..., description='Prometheus "instance" label, e.g. node-exporter:9100'),
    mountpoint: str = Query("/", description='Filesystem mountpoint for Disk (default "/")'),
    link_speed_bps: float | None = Query(None, description="Override link speed in bps; if omitted, we use node_network_speed_bytes"),
):
    cpu = current_cpu_pct(instance)
    mem = current_mem_pct(instance)
    disk = current_disk_pct(instance, mountpoint)

    util_pct = current_network_util_pct(instance, link_speed_bps)
    mbps = current_network_mbps(instance)

    return {
        "ok": True,
        "data": {
            "cpu_pct": cpu,
            "mem_pct": mem,
            "disk_pct": disk,
            "net_utilization_pct": util_pct,
            "net_mbps": mbps
        }
    }

@router.get("/cards", tags=["performance"])
def performance_cards(
    instance: str = Query(..., description='Prediction "input_features.instance", e.g. node-exporter:9100'),
    include_expired: bool = Query(False, description="Include predictions with status='Expired'"),
    mountpoint: str = Query("/", description='Filesystem mountpoint for Disk card (default "/")'),
    db: Session = Depends(get_db),
):
    """
    Return cards for metrics (CPU, Memory, Disk) that have at least one prediction.
    Each card shows current usage (from Prometheus) + prediction details (from DB).
    """
    items = []
    for metric in (CPU_METRIC, MEM_METRIC, DISK_METRIC):
        card = _build_card(db, metric, instance, include_expired, mountpoint)
        if card:
            items.append(card)
    return {"ok": True, "items": items}

# --------------------- Servers Performance list ---------------------

WARN_MIN = 70.0
CRIT_MIN = 90.0

def _health(cpu: float, mem: float, disk: float) -> dict:
    vals = [cpu, mem, disk]
    if any(v >= CRIT_MIN for v in vals):
        return {"status": "Critical", "reasons": ["metric >= 90%"]}
    if any(WARN_MIN <= v < CRIT_MIN for v in vals):
        return {"status": "Warning", "reasons": ["metric between 70% and 90%"]}
    return {"status": "Healthy", "reasons": ["all metrics < 70%"]}

def _humanize_uptime(seconds: int) -> str:
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m or not parts: parts.append(f"{m}m")
    return " ".join(parts)

@router.get("/servers/performance", tags=["performance"])
def servers_performance(db: Session = Depends(get_db)):

    # Pull all sources (non-deleted)
    sources = db.query(TelemetrySource).filter(TelemetrySource.is_deleted == False).all()

    items = []
    for s in sources:
        instance = s.name  # TelemetrySource.name == Prometheus instance

        # Live metrics from Prometheus (fail-soft to 0.0)
        try:
            cpu = float(current_cpu_pct(instance))
        except Exception:
            cpu = 0.0
        try:
            mem = float(current_mem_pct(instance))
        except Exception:
            mem = 0.0
        try:
            disk = float(current_disk_pct(instance))
        except Exception:
            disk = 0.0
        try:
            up_s = int(uptime_seconds(instance))
        except Exception:
            up_s = 0

        # Health badge: <70 Healthy, [70,90) Warning, >=90 Critical
        vals = [cpu, mem, disk]
        if any(v >= 90.0 for v in vals):
            health = {"status": "Critical", "reasons": ["metric >= 90%"]}
        elif any(70.0 <= v < 90.0 for v in vals):
            health = {"status": "Warning", "reasons": ["metric between 70% and 90%"]}
        else:
            health = {"status": "Healthy", "reasons": ["all metrics < 70%"]}

        items.append({
            "source_id": str(s.source_id),
            "display_name": s.name,                                # title
            "subtitle": getattr(s.endpoint_type, "name", None),    # e.g., "REST API"
            "instance": instance,
            "environment": getattr(s.environment, "name", None),
            "location": getattr(s.location, "name", None),
            "role": (s.metadata_info or {}).get("role"),
            "metrics": {
                "cpu_pct": round(cpu, 2),
                "mem_pct": round(mem, 2),
                "disk_pct": round(disk, 2),
            },
            "uptime": {
                "seconds": up_s,
                "human": (lambda sec: (
                    f"{sec // 86400}d {(sec % 86400) // 3600}h {((sec % 3600) // 60)}m"
                    if sec > 0 else "0m"
                ))(up_s),
            },
            "health": health,
        })

    # Sort deterministically: Critical -> Warning -> Healthy, then by CPU desc
    order = {"Critical": 0, "Warning": 1, "Healthy": 2}
    items.sort(key=lambda r: (order.get(r["health"]["status"], 3), -r["metrics"]["cpu_pct"]))

    return {"ok": True, "items": items}