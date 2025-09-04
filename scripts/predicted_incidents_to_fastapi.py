import os
import json
import time
import hashlib
from typing import Dict, Tuple, Any, Optional
from datetime import datetime, timezone

import requests
from kafka import KafkaConsumer
from app.monitor.heartbeat import start_heartbeat

hb = start_heartbeat("scripts/predicted_incidents_to_fastapi.py", interval_s=30, version="dev")

# ---------- Config ----------
API_BASE = os.getenv("POWEROPS_API", "http://localhost:8000")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:29092")
TOPIC = os.getenv("PRED_TOPIC", "predicted-incidents")
GROUP = os.getenv("GROUP_ID", "predicted-to-fastapi")
REG_PATH = os.getenv("PROPHET_REGISTRY", "models/prophet/_registry.json")

# Map metric_name → model name in your /models catalog
MODEL_NAME_BY_METRIC: Dict[str, str] = {
    "node_cpu_utilization":    "prophet-cpu",
    "node_memory_utilization": "prophet-memory",
    "node_filesystem_usage":   "prophet-disk",
    # extend later, e.g. "http_request_latency_p99": "prophet-latency"
}

# Thresholds (for explanation text; keep consistent with your predictor)
THRESHOLDS = {
    "node_cpu_utilization":    {"High": 0.85, "Critical": 0.95},
    "node_memory_utilization": {"High": 0.90, "Critical": 0.97},
    "node_filesystem_usage":   {"High": 0.90, "Critical": 0.97},
}


ENV_MODEL_IDS = {
    "prophet-cpu":    os.getenv("PROPHET_CPU_MODEL_ID"),
    "prophet-memory": os.getenv("PROPHET_MEMORY_MODEL_ID"),
    "prophet-disk":   os.getenv("PROPHET_DISK_MODEL_ID"),
}


CONSEC_REQUIRED = 3  # for explanation text (matches your predictor)


# ---------- Helpers ----------
def iso_now_z() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def get_threshold(metric: str, severity: str) -> Optional[float]:
    t = THRESHOLDS.get(metric, {})
    return t.get(severity)


def build_explanation(p: dict, threshold: Optional[float]) -> str:
    return (
        f"Forecast breach predicted for {p['metric_name']} on {p['instance']} at {p['forecast_for']}.\n"
        f"Rule: threshold={threshold if threshold is not None else 'n/a'} "
        f"breached for N={CONSEC_REQUIRED} consecutive forecast points.\n"
        f"Forecast details: yhat={p.get('yhat')}, yhat_upper={p.get('yhat_upper')}.\n"
        f"Confidence={p.get('confidence')}, method={p.get('source', 'prophet_thresholds')}."
    )


def idempotency_key(p: dict) -> str:
    base = f"{p.get('metric_name')}|{p.get('instance')}|{p.get('forecast_for')}|" \
           f"{p.get('incident_type_name')}|{p.get('severity_name')}"
    return hashlib.sha256(base.encode()).hexdigest()


def http_post(path: str, payload: dict, retries: int = 3, backoff: float = 0.8) -> dict:
    url = f"{API_BASE}{path}"
    err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            r = requests.post(url, json=payload, timeout=15)
            r.raise_for_status()
            return r.json().get("data", {})
        except Exception as e:
            err = e
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"POST {path} failed after {retries} attempts: {err}. Payload={payload}")


def http_get(path: str, params: dict, retries: int = 3, backoff: float = 0.8) -> dict:
    url = f"{API_BASE}{path}"
    err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            return r.json().get("data", {})
        except Exception as e:
            err = e
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"GET {path} failed after {retries} attempts: {err}. Params={params}")


_model_cache: Dict[str, str] = {}


def get_model_id_by_name(name: str) -> str:
    
    if ENV_MODEL_IDS.get(name):
        print(f"🧭 env override: {name} → {ENV_MODEL_IDS[name]}")
        return ENV_MODEL_IDS[name]

    
    data = http_get("/models", {"name": name})
    candidates = []
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict) and data:
        candidates = [data]

    exact = [it for it in candidates if it.get("name") == name and it.get("model_id")]
    if exact:
        mid = exact[0]["model_id"]
        print(f"🧭 resolved: {name} → {mid} (exact match in filtered query)")
        _model_cache[name] = mid
        return mid

    all_models = http_get("/models", {}) 
    if isinstance(all_models, dict):
        all_models = [all_models]
    if isinstance(all_models, list):
        exact = [it for it in all_models if it.get("name") == name and it.get("model_id")]
        if exact:
            mid = exact[0]["model_id"]
            print(f"🧭 resolved: {name} → {mid} (fallback exact match in full list)")
            _model_cache[name] = mid
            return mid

    raise RuntimeError(f"Model with exact name '{name}' not found. Create it or set PROPHET_*_MODEL_ID.")


def load_artifact_index(registry_path: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Create index: (metric, instance) -> {model_path, mae, rmse, mape}
    Uses instance = filename-without-extension (e.g., 'node-exporter:9100').
    """
    idx: Dict[Tuple[str, str], Dict[str, Any]] = {}
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            reg = json.load(f)
    except FileNotFoundError:
        return idx

    for t in reg.get("trained", []):
        metric = t.get("metric")
        model_path = t.get("model_path")
        if not (metric and model_path):
            continue
        fname = os.path.splitext(os.path.basename(model_path))[0]  # instance
        idx[(metric, fname)] = {
            "model_path": model_path,
            "mae": t.get("mae"),
            "rmse": t.get("rmse"),
            "mape": t.get("mape"),
        }
    return idx


ARTIFACT_BY_MI = load_artifact_index(REG_PATH)


def handle_predicted_message(p: dict) -> str:
    """
    p: predicted-incident message from 'predicted-incidents' topic.
       Expected keys: metric_name, instance, forecast_for, incident_type_name, severity_name,
                      yhat, yhat_upper, confidence, source, predicted_at (optional)
    Returns the created prediction_id.
    """
    metric = p["metric_name"]
    instance = p["instance"]

    # 1) Resolve model_id by metric family
    model_name = MODEL_NAME_BY_METRIC.get(metric, "prophet-cpu")
    model_id = get_model_id_by_name(model_name)

    # 2) Build and create explanation FIRST
    thr = get_threshold(metric, p.get("severity_name", "High"))
    explanation_text = build_explanation(p, thr)
    exp = http_post("/shap-explanations", {"explanation_text": explanation_text})
    explanation_id = exp.get("explanation_id")

    # 3) Enrich input_features with artifact stats if available
    art = ARTIFACT_BY_MI.get((metric, instance), {})
    input_features = {
        "metric_name": metric,
        "instance": instance,
        "forecast_for": p.get("forecast_for"),
        "threshold": thr,
        "consecutive_required": CONSEC_REQUIRED,
        "artifact_model_path": art.get("model_path"),
        "artifact_mae": art.get("mae"),
        "artifact_rmse": art.get("rmse"),
        "artifact_mape": art.get("mape"),
        "idempotency_key": idempotency_key(p),
    }

    # 4) prediction_output as the decision/result
    prediction_output = {
        "yhat": p.get("yhat"),
        "yhat_upper": p.get("yhat_upper"),
        "incident_type_name": p.get("incident_type_name"),
        "severity_name": p.get("severity_name"),
        "confidence": p.get("confidence"),
        "source": p.get("source", "prophet_thresholds"),
    }

    payload = {
        "model_id": model_id,
        "input_features": input_features,
        "prediction_output": prediction_output,
        "confidence_score": p.get("confidence"),
        "prediction_timestamp": p.get("predicted_at") or iso_now_z(),
        "incident_id": None,
        "status": "Pending",
        "explanation_id": explanation_id,
    }

    res = http_post("/predictions", payload)
    prediction_id = res.get("prediction_id") or res.get("id") or "unknown"
    return prediction_id


# ---------- Main loop ----------
def main():
    print(f"🔌 API_BASE={API_BASE}")
    print(f"🔌 KAFKA_BOOTSTRAP={KAFKA_BOOTSTRAP}")
    print(f"🔌 TOPIC={TOPIC}  GROUP={GROUP}")
    print(f"📚 REGISTRY={REG_PATH} (loaded {len(ARTIFACT_BY_MI)} artifacts)")

    # Create consumer and subscribe explicitly
    consumer = KafkaConsumer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=GROUP,
        enable_auto_commit=True,
        auto_offset_reset="latest",  # change to "earliest" if you want old msgs
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        key_deserializer=lambda b: b.decode("utf-8") if b else None,
        request_timeout_ms=30000,
        session_timeout_ms=10000,
        heartbeat_interval_ms=3000,
    )
    consumer.subscribe([TOPIC])

    print(f"🚀 Subscribed to '{TOPIC}'. Waiting for messages … (Ctrl+C to stop)")

    # Wait loop that stays alive even if topic isn't ready yet
    try:
        empty_ticks = 0
        while True:
            records = consumer.poll(timeout_ms=2000)  # 2s poll
            if not records:
                empty_ticks += 1
                if empty_ticks % 15 == 0:  # every ~30s with the 2s poll
                    # Check topic existence to help debugging
                    parts = consumer.partitions_for_topic(TOPIC)
                    if parts is None:
                        print(f"⏳ No partitions for topic '{TOPIC}' yet (topic may not exist). Still waiting…")
                    else:
                        print(f"⏳ No messages yet on '{TOPIC}' (partitions: {sorted(parts)}). Still waiting…")
                continue

            # Got something: reset idle counter and process
            empty_ticks = 0
            for tp, msgs in records.items():
                for msg in msgs:
                    p = msg.value
                    try:
                        pid = handle_predicted_message(p)
                        print(f"✔️ stored prediction_id={pid}  "
                              f"[{p.get('metric_name')}/{p.get('instance')} @ {p.get('forecast_for')}]")
                    except Exception as e:
                        print(f"❌ failed to store prediction: {e}\n   payload={json.dumps(p)}")

    except KeyboardInterrupt:
        print("\n👋 Stopping consumer…")
    finally:
        try:
            consumer.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()