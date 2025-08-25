#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, argparse
from datetime import datetime, timezone
from collections import defaultdict
from kafka import KafkaConsumer, KafkaProducer

DEFAULT_BOOTSTRAP = "localhost:29092"
IN_TOPIC  = "prophet-forecasts"
OUT_TOPIC = "predicted-incidents"

# Tune these to your SLOs
THRESHOLDS = {
    "node_cpu_utilization":     {"high": 0.85, "critical": 0.95, "incident_type": "HighCPUUsage"},
    "node_memory_utilization":  {"high": 0.90, "critical": 0.97, "incident_type": "MemoryPressure"},
    "node_filesystem_usage":    {"high": 0.90, "critical": 0.97, "incident_type": "DiskSpaceLow"},
    "http_request_latency_p99": {"high": 2.00, "critical": 5.00, "incident_type": "APILatencySLO"},
}

# Require N consecutive future points above threshold before predicting
CONSEC_REQUIRED = 3  # e.g., with 5min freq => 15 minutes

def iso_now_z():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def classify(metric: str, v: float):
    t = THRESHOLDS.get(metric)
    if not t: return None
    if v >= t["critical"]: return ("Critical", t["incident_type"])
    if v >= t["high"]:     return ("High", t["incident_type"])
    return None

def main():
    ap = argparse.ArgumentParser("Forecast → Predicted Incidents (threshold-based)")
    ap.add_argument("--bootstrap", default=DEFAULT_BOOTSTRAP)
    ap.add_argument("--in-topic",  default=IN_TOPIC)
    ap.add_argument("--out-topic", default=OUT_TOPIC)
    ap.add_argument("--consec", type=int, default=CONSEC_REQUIRED)
    ap.add_argument("--use-yhat-upper", action="store_true",
                    help="Be conservative: classify based on yhat_upper instead of yhat")
    args = ap.parse_args()

    consumer = KafkaConsumer(
        args.in_topic,
        bootstrap_servers=args.bootstrap,
        group_id="forecast-thresholds",
        enable_auto_commit=True,
        auto_offset_reset="earliest",
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        key_deserializer=lambda b: b.decode("utf-8") if b else None,
    )
    producer = KafkaProducer(
        bootstrap_servers=args.bootstrap,
        acks="all",
        linger_ms=50,
        retries=5,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
    )

    # Track consecutive qualifying forecast points for each (metric, instance)
    consec = defaultdict(int)
    last_emitted = set()  # simple in-process idempotency

    print(f"Listening on topic '{args.in_topic}' …")
    for msg in consumer:
        rec = msg.value
        metric   = rec.get("metric_name")
        instance = rec.get("instance")
        fts      = rec.get("forecast_for")  # ISO string (from your streamer)
        yhat     = float(rec.get("yhat", 0.0))
        yhi      = float(rec.get("yhat_upper", yhat))

        # choose signal: yhat (mean) or yhat_upper (conservative)
        signal = yhi if args.use_yhat_upper else yhat

        sev = classify(metric, signal)
        key = f"{metric}|{instance}"

        if sev:
            consec[key] += 1
        else:
            consec[key] = 0
            continue

        if consec[key] < args.consec:
            continue  # wait for consecutive confirmation

        severity, incident_type = sev
        # Normalize timestamp to Z if needed
        fts_z = fts if fts and fts.endswith("Z") else (fts + "Z" if fts else None)

        out = {
            "predicted_at": iso_now_z(),
            "forecast_for": fts_z,
            "metric_name": metric,
            "instance": instance,
            "incident_type_name": incident_type,
            "severity_name": severity,
            "yhat": yhat,
            "yhat_upper": yhi,
            "confidence": 0.9 if severity == "Critical" else 0.75,
            "source": "prophet_thresholds",
            "id": f"{metric}|{instance}|{fts_z}",
        }

        if out["id"] in last_emitted:
            continue
        last_emitted.add(out["id"])

        producer.send(args.out_topic, key=key, value=out)
        print(f"→ predicted incident: {incident_type} {severity} @ {fts_z} for {metric}/{instance}")

    producer.flush()

if __name__ == "__main__":
    main()
