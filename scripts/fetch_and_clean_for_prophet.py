"""
Fetch derived metrics from Prometheus (based on metric_recipes.yaml),
clean to Prophet-ready series, and write Parquet partitions (or CSV).

Config:
  - app/config/env.yaml
      env: dev-local | prod-company
      prom_url: https://prometheus...
      step: 60s
      rate_window: 5m
      aliases_enabled: true|false
      aliases_file: app/config/aliases.yaml
      recipes_file: app/config/metric_recipes.yaml

  - app/config/metric_recipes.yaml
      metrics:
        - name: node_cpu_utilization
          promql: |
            1 - avg by(instance) (
              rate(node_cpu_seconds_total{mode="idle"}[5m])
            )
          unit: ratio
          clip: [0, 1]
          resample: 60s
          aggregation: by(instance)
          incident_type: HighCPUUsage
        ...

  - app/config/aliases.yaml
      aliases:
        node-exporter-01.u-cloudsolutions.xyz: node-exporter:9100
        node-exporter-02.u-cloudsolutions.xyz: node-exporter:9100
        cadvisor-01.u-cloudsolutions.xyz: cadvisor:8080
        cadvisor-02.u-cloudsolutions.xyz: cadvisor:8080
        node-exporter:9100: node-exporter:9100
        cadvisor:8080: cadvisor:8080

Outputs (default Parquet):
  data/prophet_ready/
    metric=<metric>/instance=<instance_id>/date=YYYY-MM-DD/part-<unix>.parquet

Manifests (one per {metric, instance_id}):
  manifests/<metric>/<instance_id>.json

Usage examples:
  # Last 30 days, Parquet, configs from env.yaml
  python scripts/fetch_and_clean_for_prophet.py \
    --env-file app/config/env.yaml \
    --lookback-days 30 \
    --parquet

  # Explicit window
  python scripts/fetch_and_clean_for_prophet.py \
    --env-file app/config/env.yaml \
    --start "2025-07-20T00:00:00Z" \
    --end   "2025-08-20T00:00:00Z" \
    --parquet
"""

import os
import re
import time
import json
import math
import argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional

import requests
import numpy as np
import pandas as pd
from app.monitor.heartbeat import start_heartbeat

try:
    import yaml
except Exception as e:
    raise RuntimeError(
        "PyYAML is required. Install with: pip install pyyaml"
    ) from e

hb = start_heartbeat("scripts/fetch_and_clean_for_prophet.py", interval_s=30, version="dev")

# ---------- Defaults & helpers ----------
MAX_CHUNK_HOURS = 24
REQ_TIMEOUT = 60
RETRY_ATTEMPTS = 3
RETRY_BACKOFFS = [1, 3, 9]  # seconds

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def iso_to_utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)

def sanitize(s):
    if s is None:
        s = "unknown"
    try:
        if isinstance(s, float) and math.isnan(s):
            s = "unknown"
    except Exception:
        pass
    return re.sub(r"[^a-zA-Z0-9._:@-]+", "_", str(s))

def chunks(start: datetime, end: datetime, hours: int):
    cur = start
    step = timedelta(hours=hours)
    while cur < end:
        nxt = min(cur + step, end)
        yield cur, nxt
        cur = nxt

def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


# ---------- Config loaders ----------
def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def load_env(env_file: str) -> dict:
    cfg = load_yaml(env_file)
    # minimal validation
    for k in ["env", "prom_url", "step", "rate_window", "aliases_enabled", "recipes_file"]:
        if k not in cfg:
            raise ValueError(f"[env.yaml] missing required key: {k}")
    return cfg

def load_recipes(recipes_file: str) -> List[dict]:
    cfg = load_yaml(recipes_file)
    metrics = cfg.get("metrics", [])
    if not metrics:
        raise ValueError(f"[metric_recipes.yaml] no 'metrics' entries found")
    # normalize entries
    out = []
    for m in metrics:
        for req in ["name", "promql", "unit", "resample"]:
            if req not in m:
                raise ValueError(f"[metric_recipes.yaml] metric missing field '{req}': {m}")
        # clip optional
        clip = m.get("clip", None)
        if clip is not None and (not isinstance(clip, list) or len(clip) != 2):
            raise ValueError(f"[metric_recipes.yaml] 'clip' must be [min,max] for {m.get('name')}")
        out.append(m)
    return out

def load_aliases(aliases_file: Optional[str], enabled: bool) -> Dict[str, str]:
    if not enabled or not aliases_file:
        return {}
    cfg = load_yaml(aliases_file)
    return cfg.get("aliases", {}) or {}


# ---------- Prometheus HTTP ----------
def auth_kwargs() -> Dict:
    headers = {}
    tok = os.getenv("PROMETHEUS_BEARER_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    auth = None
    u, p = os.getenv("PROMETHEUS_BASIC_USER"), os.getenv("PROMETHEUS_BASIC_PASS")
    if u and p:
        auth = (u, p)
    return {"headers": headers, "auth": auth, "timeout": REQ_TIMEOUT}

def query_range(prom_url: str, expr: str, start: datetime, end: datetime, step: str) -> List[Dict]:
    """Run query_range in daily chunks, merge results by metric label-set."""
    merged: Dict[Tuple, Dict] = {}

    for a, b in chunks(start, end, MAX_CHUNK_HOURS):
        url = f"{prom_url.rstrip('/')}/api/v1/query_range"
        params = {"query": expr, "start": int(a.timestamp()), "end": int(b.timestamp()), "step": step}
        last_err = None
        for attempt in range(RETRY_ATTEMPTS):
            try:
                r = requests.get(url, params=params, **auth_kwargs())
                r.raise_for_status()
                payload = r.json()
                if payload.get("status") != "success":
                    raise RuntimeError(f"Prometheus error: {payload}")
                for s in payload["data"]["result"]:
                    key = tuple(sorted(s.get("metric", {}).items()))
                    merged.setdefault(key, {"metric": s.get("metric", {}), "values": []})
                    merged[key]["values"].extend(s.get("values", []))
                break
            except Exception as e:
                last_err = e
                if attempt < RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_BACKOFFS[attempt])
                else:
                    raise last_err
        time.sleep(0.1)  # tiny politeness delay

    out = []
    for _, v in merged.items():
        seen, vals = set(), []
        for ts, y in v["values"]:
            if ts not in seen:
                seen.add(ts)
                vals.append([ts, y])
        vals.sort(key=lambda t: float(t[0]))
        out.append({"metric": v["metric"], "values": vals})
    return out


# ---------- Frame shaping & cleaning ----------
def extract_instance_label(labels: Dict[str, str]) -> str:
    return (
        labels.get("instance")
        or labels.get("pod")
        or labels.get("container")
        or labels.get("name")
        or labels.get("device")
        or labels.get("id")
        or "unknown"
    )

def apply_alias(instance: str, aliases: Dict[str, str]) -> str:
    return aliases.get(instance, instance)

def to_df(series: Dict, canonical_metric_name: str, aliases: Dict[str, str], aliases_enabled: bool) -> Optional[pd.DataFrame]:
    labels = series.get("metric", {})
    values = series.get("values", [])
    if not values:
        return None

    df = pd.DataFrame(values, columns=["ts", "y"])
    df["ts"] = df["ts"].astype(float)
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    df.dropna(subset=["y"], inplace=True)
    df["ds"] = pd.to_datetime(df["ts"], unit="s", utc=True)

    inst_raw = str(extract_instance_label(labels))
    inst = apply_alias(inst_raw, aliases) if aliases_enabled else inst_raw

    df["metric"] = canonical_metric_name
    df["instance"] = inst
    return df[["ds", "y", "metric", "instance"]]

def clean_for_prophet(
    df: pd.DataFrame,
    resample: str,
    clip_min: Optional[float] = None,
    clip_max: Optional[float] = None,
    max_gap: int = 5,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    df = df.sort_values("ds").drop_duplicates("ds").set_index("ds").asfreq(resample)
    df["y"] = pd.to_numeric(df["y"], errors="coerce")

    # Clip to expected range (per recipe)
    if clip_min is not None:
        df.loc[df["y"] < clip_min, "y"] = clip_min
    if clip_max is not None:
        df.loc[df["y"] > clip_max, "y"] = clip_max

    # Negative guard
    df.loc[df["y"] < 0, "y"] = np.nan

    # MAD-based outlier suppression
    y = df["y"].copy()
    med = np.nanmedian(y)
    mad = np.nanmedian(np.abs(y - med)) or 0.0
    if mad > 0:
        z = 0.6745 * (y - med) / mad
        df.loc[np.abs(z) > 6, "y"] = np.nan

    # Fill short gaps
    df["y"] = df["y"].interpolate(limit=max_gap, limit_direction="both")

    df = df.dropna(subset=["y"]).reset_index()
    return df[["ds", "y", "metric", "instance"]]


# ---------- Writers ----------
def save_csv(out_dir: str, metric: str, instance: str, df: pd.DataFrame) -> str:
    d = os.path.join(out_dir, metric)
    ensure_dir(d)
    path = os.path.join(d, f"{sanitize(instance)}.csv")
    df[["ds", "y", "metric", "instance"]].to_csv(path, index=False)
    return path

def save_parquet_partitioned(out_dir: str, metric: str, instance: str, df: pd.DataFrame) -> List[str]:
    paths = []
    df["date"] = df["ds"].dt.date
    for date, chunk in df.groupby("date"):
        d = os.path.join(
            out_dir,
            f"metric={metric}",
            f"instance={sanitize(instance)}",
            f"date={date.isoformat()}",
        )
        ensure_dir(d)
        path = os.path.join(d, f"part-{int(pd.to_datetime(chunk['ds'].max()).timestamp())}.parquet")
        # Use default snappy compression if available (pandas + pyarrow handle)
        chunk[["ds", "y", "metric", "instance"]].to_parquet(path, index=False)
        paths.append(path)
    return paths

def write_manifest(manif_root: str, metric: str, instance: str, manifest: Dict):
    d = os.path.join(manif_root, metric)
    ensure_dir(d)
    path = os.path.join(d, f"{sanitize(instance)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return path


# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser("Fetch + clean Prometheus series → Prophet-ready data (using recipes).")

    # Primary config
    ap.add_argument("--env-file", default="app/config/env.yaml", help="Path to env.yaml")
    ap.add_argument("--recipes-file", default=None, help="Override recipes file (else from env.yaml)")
    ap.add_argument("--aliases-file", default=None, help="Override aliases file (else from env.yaml)")

    # Time window
    ap.add_argument("--start", help='ISO, e.g. "2025-07-01T00:00:00Z"')
    ap.add_argument("--end", help='ISO, e.g. "2025-08-19T00:00:00Z"')
    ap.add_argument("--lookback-days", type=int, default=None, help="If set, ignore --start/--end and fetch last N days")

    # Output
    ap.add_argument("--out", default="data/prophet_ready", help="Output dir for series")
    ap.add_argument("--manifests-out", default="manifests", help="Output dir for manifests")
    ap.add_argument("--parquet", action="store_true", help="Write partitioned Parquet (default if set); else CSV")
    ap.add_argument("--csv", action="store_true", help="Force CSV output (overrides --parquet)")

    # Overrides
    ap.add_argument("--prom-url", default=None, help="Override Prometheus URL")
    ap.add_argument("--step", default=None, help="Override query step (e.g., 60s)")
    ap.add_argument("--rate-window", default=None, help="Override rate window (e.g., 5m)")
    ap.add_argument("--aliases-enabled", type=str, default=None, help="Override aliasing: true|false")

    args = ap.parse_args()

    # Load env/configs
    env_cfg = load_env(args.env_file)
    prom_url = args.prom_url or env_cfg["prom_url"]
    global_step = args.step or env_cfg["step"]
    global_rate_window = args.rate_window or env_cfg["rate_window"]

    if args.aliases_enabled is None:
        aliases_enabled = bool(env_cfg.get("aliases_enabled", False))
    else:
        aliases_enabled = args.aliases_enabled.lower() == "true"

    recipes_file = args.recipes_file or env_cfg["recipes_file"]
    aliases_file = args.aliases_file or env_cfg.get("aliases_file", None)

    recipes = load_recipes(recipes_file)
    aliases = load_aliases(aliases_file, aliases_enabled)

    # Time window
    if args.lookback_days is not None:
        end_dt = now_utc()
        start_dt = end_dt - timedelta(days=int(args.lookback_days))
    else:
        if not args.start or not args.end:
            raise ValueError("Provide --lookback-days OR both --start and --end")
        start_dt = iso_to_utc(args.start)
        end_dt = iso_to_utc(args.end)

    if end_dt <= start_dt:
        raise ValueError("end must be > start")

    # Output mode
    write_parquet = True
    if args.csv:
        write_parquet = False
    elif args.parquet:
        write_parquet = True

    print(f"Environment : {env_cfg['env']}")
    print(f"Prometheus  : {prom_url}")
    print(f"Window      : {start_dt.isoformat()} → {end_dt.isoformat()}")
    print(f"Query step  : {global_step}")
    print(f"Rate window : {global_rate_window}")
    print(f"Aliasing    : {'ENABLED' if aliases_enabled else 'DISABLED'}")
    print(f"Recipes     : {recipes_file}")
    print(f"Aliases     : {aliases_file if aliases_file else '(none)'}")
    print(f"Output      : {args.out} ({'Parquet' if write_parquet else 'CSV'})")
    print("--------------------------------------------------------------")

    wrote_series = 0

    for recipe in recipes:
        name = recipe["name"]
        promql = str(recipe["promql"])
        unit = recipe["unit"]
        resample = recipe["resample"]
        clip = recipe.get("clip", None)

        # Optional templating if user includes {{rate_window}} or {{step}} in YAML
        promql = promql.replace("{{rate_window}}", global_rate_window).replace("{{step}}", global_step)

        print(f"\n[Metric] {name}")
        print(f"PromQL:\n{promql.strip()}")

        try:
            series_list = query_range(prom_url, promql, start_dt, end_dt, global_step)
        except Exception as e:
            print(f"  ! query failed: {e}")
            continue

        if not series_list:
            print("  (no data)")
            continue

        # Build frames per returned label set
        for s in series_list:
            raw_df = to_df(s, name, aliases, aliases_enabled)
            if raw_df is None or raw_df.empty:
                continue

            clip_min = clip[0] if clip else None
            clip_max = clip[1] if clip else None

            cleaned = clean_for_prophet(raw_df, resample=resample, clip_min=clip_min, clip_max=clip_max)
            if cleaned is None or cleaned.empty:
                continue

            instance_id = cleaned["instance"].iloc[0]

            if write_parquet:
                paths = save_parquet_partitioned(args.out, name, instance_id, cleaned)
                for p in paths:
                    print(f"  ✓ {p} (+{len(cleaned)})")
            else:
                path = save_csv(args.out, name, instance_id, cleaned)
                print(f"  ✓ {path} ({len(cleaned)} rows)")

            # Write/update manifest
            manifest = {
                "env": env_cfg["env"],
                "metric": name,
                "unit": unit,
                "resample": resample,
                "clip": clip,
                "prom_url": prom_url,
                "promql": promql,
                "query_step": global_step,
                "rate_window": global_rate_window,
                "instance": instance_id,
                "time_range": {
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                },
                "aliases_enabled": aliases_enabled,
                "generated_at": now_utc().isoformat(),
            }
            man_path = write_manifest(args.manifests_out, name, instance_id, manifest)
            print(f"  ↳ manifest: {man_path}")

            wrote_series += 1

    if wrote_series == 0:
        print("\nNo Prophet-ready files written. Check configs, time window, PromQL, or auth.")
    else:
        print(f"\nDone. Wrote {wrote_series} Prophet-ready series.")
        print("Manifests recorded under:", args.manifests_out)


if __name__ == "__main__":
    main()
