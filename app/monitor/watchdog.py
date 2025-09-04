# app/monitor/watchdog.py
import os
import json
import time
import threading
import datetime as dt
from collections import defaultdict
from fastapi import APIRouter, Response

router = APIRouter()

# ---------- Config (via env) ----------
HEARTBEAT_BUS = os.getenv("HEARTBEAT_BUS", "queue_incident.jsonl")
TTL_SECONDS = int(os.getenv("HEARTBEAT_TTL", "90"))
START_AT_END = os.getenv("HEARTBEAT_START_AT_END", "0") == "1"
# NEW: control name normalization and HTTP status behavior (default: normalize & always 200)
NORMALIZE_SOURCE_NAMES = os.getenv("HEARTBEAT_NORMALIZE_NAMES", "1") == "1"
ALWAYS_HTTP_200 = os.getenv("HEARTBEAT_ALWAYS_HTTP_200", "1") == "1"

# ---------- In-memory state ----------
state = {
    "last_seen": defaultdict(lambda: None),   # display_name -> ts (epoch)
    "meta": defaultdict(dict),                # display_name -> last payload
    "errors": []                              
}
_started = False


# ---------- Helpers ----------
def _normalize_source(src: str) -> str:
    """Collapse 'path/to/script.py' -> 'script' if NORMALIZE_SOURCE_NAMES is on."""
    if not src:
        return "unknown"
    if not NORMALIZE_SOURCE_NAMES:
        return src
    base = os.path.basename(src)         # script.py
    name, _ext = os.path.splitext(base)  # script
    return name or src

def _parse_ts_utc(ts: str) -> float:
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        try:
            return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=dt.timezone.utc).timestamp()
        except Exception:
            try:
                return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
            except Exception:
                return time.time()

def _process_line(line: str):
    try:
        evt = json.loads(line)
    except Exception:
        return
    if evt.get("type") != "heartbeat":
        return
    raw_src = evt.get("source", "unknown")
    src = _normalize_source(raw_src)
    ts = evt.get("ts")
    payload = evt.get("payload", {}) or {}
    t = _parse_ts_utc(ts) if ts else time.time()
    state["last_seen"][src] = t
    # keep original name in meta for debugging, but don’t break frontend shape
    meta = dict(payload)
    meta.setdefault("_raw_source", raw_src)
    state["meta"][src] = meta

def _tail_file(path: str):
    while not os.path.exists(path):
        time.sleep(0.5)
    f = open(path, "r", encoding="utf-8", errors="ignore")
    if START_AT_END:
        f.seek(0, os.SEEK_END)
    buf = ""
    while True:
        chunk = f.read()
        if not chunk:
            try:
                cur_pos = f.tell()
                f_stat = os.stat(path)
                if cur_pos > f_stat.st_size:
                    f.close()
                    f = open(path, "r", encoding="utf-8", errors="ignore")
                    if START_AT_END:
                        f.seek(0, os.SEEK_END)
            except Exception as e:
                state["errors"] = (state["errors"] + [f"tail_error:{e}"])[-10:]
                while not os.path.exists(path):
                    time.sleep(0.5)
                try:
                    f = open(path, "r", encoding="utf-8", errors="ignore")
                    if START_AT_END:
                        f.seek(0, os.SEEK_END)
                except Exception:
                    pass
            time.sleep(0.5)
            continue

        buf += chunk
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            if line.strip():
                _process_line(line)

def start_watchdog():
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_tail_file, args=(HEARTBEAT_BUS,), daemon=True)
    t.start()

# ---------- Routes ----------
@router.get("/health")
def orchestrator_health(resp: Response):
    now = time.time()
    components = {}
    up_count = 0
    degraded_count = 0
    down_count = 0

    for src, last in state["last_seen"].items():
        age = None if last is None else now - last
        if age is None or age > TTL_SECONDS:
            status_s = "down"
            down_count += 1
        elif age > (TTL_SECONDS / 2):
            status_s = "degraded"
            degraded_count += 1
        else:
            status_s = "ok"
            up_count += 1

        components[src] = {
            "status": status_s,
            "last_seen_s": None if age is None else int(age),
            "meta": state["meta"].get(src, {})
        }

    if not components:
        overall = "down"
    else:
        all_ok = all(v["status"] == "ok" for v in components.values())
        any_degraded = any(v["status"] == "degraded" for v in components.values())
        overall = "ok" if all_ok else ("degraded" if any_degraded else "down")

    # Always 200 unless you explicitly disable it
    if not ALWAYS_HTTP_200 and overall != "ok":
        # legacy behavior: set 503 when unhealthy (only if env flag says so)
        from fastapi import status as http_status
        resp.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "overall": overall,
        "counts": {"ok": up_count, "degraded": degraded_count, "down": down_count},
        "ttl_seconds": TTL_SECONDS,
        "components": components,
        "ts": int(now)
    }

@router.get("/health/debug")
def health_debug():
    return {
        "heartbeat_bus": HEARTBEAT_BUS,
        "ttl_seconds": TTL_SECONDS,
        "start_at_end": START_AT_END,
        "normalize_names": NORMALIZE_SOURCE_NAMES,
        "always_http_200": ALWAYS_HTTP_200,
        "errors": state["errors"][-5:]
    }
