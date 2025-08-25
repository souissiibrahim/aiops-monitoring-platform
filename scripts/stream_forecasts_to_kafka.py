#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, glob, argparse, pickle, time
import pandas as pd
from kafka import KafkaProducer

DEFAULT_MODEL_ROOT = "models/prophet"
DEFAULT_HORIZON    = "48h"
DEFAULT_FREQ       = "5min"
DEFAULT_TOPIC      = "prophet-forecasts"
DEFAULT_BOOTSTRAP  = "localhost:29092"
REGISTRY_NAME      = "_registry.json"

def list_models(model_root: str):
    """Prefer the training registry; fallback to globbing .pkl files."""
    reg_path = os.path.join(model_root, REGISTRY_NAME)
    items = []
    if os.path.exists(reg_path):
        with open(reg_path, "r", encoding="utf-8") as f:
            reg = json.load(f)
        for t in reg.get("trained", []):
            items.append((t["metric"], t["instance"], t["model_path"]))
        if items:
            return items

    for metric_dir in glob.glob(os.path.join(model_root, "*")):
        if not os.path.isdir(metric_dir):
            continue
        metric = os.path.basename(metric_dir)
        for pkl in glob.glob(os.path.join(metric_dir, "*.pkl")):
            instance = os.path.splitext(os.path.basename(pkl))[0]
            items.append((metric, instance, pkl))
    return items

def periods_from(horizon: str, freq: str) -> int:
    """horizon '24h'/'48h'/'7d'; freq '60s'/'5min'/'1h'."""
    hz = horizon.strip().lower()
    if hz.endswith("h"):
        total_seconds = int(hz[:-1]) * 3600
    elif hz.endswith("d"):
        total_seconds = int(hz[:-1]) * 86400
    else:
        raise ValueError("Unsupported horizon. Use '24h', '48h', '7d', etc.")
    step_seconds = int(pd.to_timedelta(freq).total_seconds())
    if step_seconds <= 0:
        raise ValueError("Invalid freq.")
    return max(1, total_seconds // step_seconds)

def forecast_df(pkl_path: str, horizon: str, freq: str) -> pd.DataFrame:
    with open(pkl_path, "rb") as f:
        blob = pickle.load(f)
    m = blob["model"]
    meta = blob.get("meta", {})
    bounded = bool(meta.get("bounded_0_1", False))

    n_periods = periods_from(horizon, freq)
    future = m.make_future_dataframe(periods=n_periods, freq=freq, include_history=False)
    if bounded:
        future["cap"] = 1.0
        future["floor"] = 0.0

    fc = m.predict(future)[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
    return fc, meta

def json_records(metric: str, instance: str, fc: pd.DataFrame, source: str = "prophet"):
    # Convert to JSON-ready rows
    for _, r in fc.iterrows():
        ds = r["ds"]
        # ISO string (ensure str if it's Timestamp)
        ds_iso = ds.isoformat() if hasattr(ds, "isoformat") else str(ds)
        yield {
            "source": source,
            "metric_name": metric,
            "instance": instance,
            "forecast_for": ds_iso,           # future timestamp
            "yhat": float(r["yhat"]),
            "yhat_lower": float(r["yhat_lower"]),
            "yhat_upper": float(r["yhat_upper"]),
            # handy composite id to help idempotency on consumers
            "id": f"{metric}|{instance}|{ds_iso}"
        }

def build_producer(bootstrap: str) -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=bootstrap,
        acks="all",
        linger_ms=200,
        retries=5,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if isinstance(k, str) else k,
    )

def main():
    ap = argparse.ArgumentParser("Stream Prophet forecasts to Kafka")
    ap.add_argument("--model-root", default=DEFAULT_MODEL_ROOT, help="Folder with saved Prophet models")
    ap.add_argument("--horizon", default=DEFAULT_HORIZON, help="Forecast horizon, e.g. '24h','48h','7d'")
    ap.add_argument("--freq", default=DEFAULT_FREQ, help="Resolution per point, e.g. '60s','5min','1h'")
    ap.add_argument("--topic", default=DEFAULT_TOPIC, help="Kafka topic to produce to")
    ap.add_argument("--bootstrap", default=DEFAULT_BOOTSTRAP, help="Kafka bootstrap servers")
    ap.add_argument("--filter-metric", default=None, help="Only stream this metric")
    ap.add_argument("--filter-instance", default=None, help="Only stream this instance")
    args = ap.parse_args()

    items = list_models(args.model_root)
    if not items:
        print("No models found.")
        return

    producer = build_producer(args.bootstrap)
    total = 0

    for metric, instance, pkl in items:
        if args.filter_metric and metric != args.filter_metric:
            continue
        if args.filter_instance and instance != args.filter_instance:
            continue

        try:
            fc, meta = forecast_df(pkl, args.horizon, args.freq)
        except Exception as e:
            print(f"! forecast failed for {metric}/{instance}: {e}")
            continue

        for rec in json_records(metric, instance, fc):
            key = f"{metric}|{instance}"
            producer.send(args.topic, key=key, value=rec)
            total += 1

        print(f"→ streamed {len(fc)} messages for {metric}/{instance} to topic '{args.topic}'")

    producer.flush()
    print(f"✅ Done. Total messages: {total}")

if __name__ == "__main__":
    main()
