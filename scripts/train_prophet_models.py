#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, glob, json, pickle, argparse, warnings
from datetime import timedelta
import numpy as np
import pandas as pd
from prophet import Prophet


DEFAULT_INROOT  = "data/prophet_ready_csv"
#DEFAULT_INROOT  = "data/prophet_ready"
DEFAULT_OUTROOT = "models/prophet"
REGISTRY_NAME   = "_registry.json"

MIN_POINTS = 500  # ~8h @60s; skip if fewer points


def safe_make_dir(p: str):
    os.makedirs(p, exist_ok=True)


def is_utilization_metric(metric_name: str) -> bool:
    """Bounded [0,1] metrics → enable logistic caps."""
    m = (metric_name or "").lower()
    return any(k in m for k in [
        "cpu_utilization", "memory_utilization",
        "filesystem_usage", "disk_usage", "utilization", "usage"
    ])


def _compute_errors(y_true, y_hat) -> dict:
    y = pd.Series(pd.to_numeric(y_true, errors="coerce"))
    yh = pd.Series(pd.to_numeric(y_hat, errors="coerce"))
    m = pd.DataFrame({"y": y, "yh": yh}).dropna()
    if m.empty:
        return {"mae": None, "rmse": None, "mape": None}
    mae  = float((m["y"] - m["yh"]).abs().mean())
    rmse = float(np.sqrt(((m["y"] - m["yh"]) ** 2).mean()))
    mape = float(((m["y"] - m["yh"]).abs() / m["y"].clip(lower=1e-9)).clip(upper=5).mean())
    return {"mae": mae, "rmse": rmse, "mape": mape}


def train_one(csv_path: str, downsample: str | None = None):
    """Train a Prophet model on a single CSV series and return (info, reason)."""

    # ---- load & basic cleaning
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        return None, f"read_failed:{e}"

    if not {"ds", "y"}.issubset(df.columns):
        return None, "missing_columns"

    df["y"]  = pd.to_numeric(df["y"], errors="coerce")
    df["ds"] = pd.to_datetime(df["ds"], errors="coerce", utc=True).dt.tz_convert(None)
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["ds", "y"])
    if df.empty:
        return None, "empty_after_clean"

    # guards
    df = df.sort_values("ds").drop_duplicates("ds")
    if len(df) < MIN_POINTS:
        return None, "too_few_points"
    if (df["ds"].max() - df["ds"].min()) < timedelta(days=3):
        return None, "window_too_short"
    if df["y"].nunique() <= 1:
        return None, "no_variation"

    # identify metric/instance
    metric = (str(df["metric"].iloc[0]).strip()
              if "metric" in df.columns and isinstance(df["metric"].iloc[0], str)
              else os.path.basename(os.path.dirname(csv_path)))
    instance = (str(df["instance"].iloc[0]).strip()
                if "instance" in df.columns and isinstance(df["instance"].iloc[0], str)
                else os.path.splitext(os.path.basename(csv_path))[0])

    # optional downsample (e.g., '5min', '1h')
    if downsample:
        df = (
            df.set_index("ds")[["y"]]
              .resample(downsample).mean()
              .dropna()
              .reset_index()
        )

    # ---- model config
    bounded = is_utilization_metric(metric)
    if bounded:
        # keep forecasts in [0,1]
        df["cap"]   = 1.0
        df["floor"] = 0.0
        m = Prophet(
            growth="logistic",
            seasonality_mode="multiplicative",
            changepoint_prior_scale=0.05,
            daily_seasonality=False,
            weekly_seasonality=False,
        )
        fit_cols = ["ds", "y", "cap", "floor"]
    else:
        m = Prophet(
            seasonality_mode="additive",
            changepoint_prior_scale=0.05,
            daily_seasonality=False,
            weekly_seasonality=False,
        )
        fit_cols = ["ds", "y"]

    m.add_seasonality(name="daily",  period=1, fourier_order=8)
    m.add_seasonality(name="weekly", period=7, fourier_order=6)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m.fit(df[fit_cols])

    # ---- holdout validation: 7 days (fallback to 1 if span too short)
    span_days = (df["ds"].max() - df["ds"].min()).days
    holdout_days = 7 if span_days >= 8 else 1
    cutoff = df["ds"].max() - timedelta(days=holdout_days)
    val = df[df["ds"] > cutoff].copy()
    if not val.empty:
        pred_cols = ["ds"] + (["cap", "floor"] if bounded else [])
        fc = m.predict(val[pred_cols])
        merged = val.merge(fc[["ds", "yhat"]], on="ds", how="left")
        errors = _compute_errors(merged["y"], merged["yhat"])
    else:
        errors = {"mae": None, "rmse": None, "mape": None}

    # ---- save artifacts
    outdir = os.path.join(DEFAULT_OUTROOT, metric)
    safe_make_dir(outdir)
    model_path = os.path.join(outdir, f"{instance}.pkl")

    with open(model_path, "wb") as f:
        pickle.dump({
            "model": m,
            "meta": {
                "metric": metric,
                "instance": instance,
                "rows": int(len(df)),
                "ds_start": df["ds"].min().isoformat(),
                "ds_end": df["ds"].max().isoformat(),
                "downsample": downsample or "none",
                "bounded_0_1": bounded,
                "validation_window_days": holdout_days,
                "errors": errors,
            }
        }, f)

    return {
        "metric": metric,
        "instance": instance,
        "model_path": model_path,
        "rows": int(len(df)),
        "mae":  errors["mae"],
        "rmse": errors["rmse"],
        "mape": errors["mape"],
    }, None


def main():
    ap = argparse.ArgumentParser("Train Prophet models from cleaned CSVs")
    ap.add_argument("--inroot", default=DEFAULT_INROOT, help="Root folder of CSVs (metric/instance.csv)")
    ap.add_argument("--outroot", default=DEFAULT_OUTROOT, help="Where to write models")
    ap.add_argument("--downsample", default=None, help="Optional resample (e.g., '5min', '1h')")
    args = ap.parse_args()

    inroot  = args.inroot
    outroot = args.outroot
    down    = args.downsample

    safe_make_dir(outroot)

    registry = {"trained": [], "skipped": []}

    metric_dirs = sorted(glob.glob(os.path.join(inroot, "*")))
    if not metric_dirs:
        print(f"No metric folders found under {inroot}")

    for metric_dir in metric_dirs:
        metric = os.path.basename(metric_dir)
        for csv_path in sorted(glob.glob(os.path.join(metric_dir, "*.csv"))):
            info, reason = train_one(csv_path, downsample=down)
            if info:
                mae  = "NA" if info["mae"]  is None else f"{info['mae']:.6f}"
                rmse = "NA" if info["rmse"] is None else f"{info['rmse']:.6f}"
                mape = "NA" if info["mape"] is None else f"{info['mape']:.6f}"
                print(f"✓ {info['metric']}/{info['instance']}  rows={info['rows']}  "
                      f"MAE={mae} RMSE={rmse} MAPE={mape}")
                registry["trained"].append(info)
            else:
                base = os.path.splitext(os.path.basename(csv_path))[0]
                print(f"- skipped {metric}/{base}  ({reason})")
                registry["skipped"].append({"metric": metric, "instance": base, "reason": reason})

    reg_path = os.path.join(outroot, REGISTRY_NAME)
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)

    print(f"\nModels written to: {outroot}")
    print(f"Registry: {reg_path}")


if __name__ == "__main__":
    main()
