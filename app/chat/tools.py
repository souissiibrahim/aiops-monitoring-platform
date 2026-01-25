import os, requests, datetime as dt
API  = os.getenv("POWEROPS_API", "http://adress_loc:8000")
PROM = os.getenv("PROM_URL", "http://adress_loc:9090")
LOKI = os.getenv("LOKI_URL", "http://adress_loc:3100")

def get_incident(incident_id):
    r = requests.get(f"{API}/incidents/{incident_id}", timeout=10); r.raise_for_status(); return r.json()["data"]

def get_latest_incidents(limit=3):
    r = requests.get(f"{API}/incidents", params={"limit":limit,"order":"desc"}, timeout=10)
    r.raise_for_status(); return r.json()["data"]

def get_prediction_for_incident(incident_id):
    r = requests.get(f"{API}/predictions/by-incident/{incident_id}", timeout=10)
    return None if r.status_code==404 else r.json().get("data")

def get_rca(incident_id):
    r = requests.get(f"{API}/rca/{incident_id}", timeout=10)
    return r.json().get("data")

def prom_instant(query: str):
    print(f"[DEBUG] Calling Prometheus instant query: {query}")
    r = requests.get(f"{PROM}/api/v1/query", params={"query": query}, timeout=10)
    r.raise_for_status(); return r.json(), query

def prom_range(query: str, start_iso: str, end_iso: str, step="30s"):
    print(f"[DEBUG] Calling Prometheus range query: {query}, {start_iso} → {end_iso}")      
    r = requests.get(f"{PROM}/api/v1/query_range",
                     params={"query":query,"start":start_iso,"end":end_iso,"step":step}, timeout=15)
    r.raise_for_status(); return r.json(), query

def _to_ns(iso: str) -> int:
    t = dt.datetime.fromisoformat(iso.replace("Z","+00:00")); return int(t.timestamp()*1e9)

def loki_range(query: str, start_iso: str, end_iso: str, limit=400, direction="backward"):
    print(f"[DEBUG] Calling Loki: {query}, {start_iso} → {end_iso}, limit={limit}")
    r = requests.get(f"{LOKI}/loki/api/v1/query_range",
        params={"query":query,"start":_to_ns(start_iso),"end":_to_ns(end_iso),"limit":limit,"direction":direction},
        timeout=15)
    r.raise_for_status(); return r.json(), query

def get_runbooks():
    """GET /runbooks"""
    r = _S.get(f"{API}/runbooks", timeout=10, verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json().get("data", [])

def get_runbook_by_id(runbook_id: str):
    """GET /runbooks/{runbook_id}"""
    r = _S.get(f"{API}/runbooks/{runbook_id}", timeout=10, verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json().get("data")

def get_runbook_steps(runbook_id: str):
    """GET /runbook/{runbook_id}/steps  (note: singular 'runbook' per your router)"""
    r = _S.get(f"{API}/runbook/{runbook_id}/steps", timeout=10, verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json().get("data", [])

def get_runbook_counts():
    """GET /runbooks/count and /runbooks/count/running"""
    total = _S.get(f"{API}/runbooks/count", timeout=6, verify=VERIFY_SSL)
    total.raise_for_status()
    running = _S.get(f"{API}/runbooks/count/running", timeout=6, verify=VERIFY_SSL)
    running.raise_for_status()
    return {
        "total": total.json().get("data", {}).get("total"),
        "running_now": running.json().get("data", {}).get("running_now"),
    }

def get_runbook_last_run(runbook_id: str):
    """GET /runbooks/{runbook_id}/last-run"""
    r = _S.get(f"{API}/runbooks/{runbook_id}/last-run", timeout=8, verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json().get("data", {}).get("last_run")

def get_runbook_last_completed(runbook_id: str):
    """GET /runbooks/{runbook_id}/last-completed"""
    r = _S.get(f"{API}/runbooks/{runbook_id}/last-completed", timeout=8, verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json().get("data", {}).get("last_completed")


def get_runbook_avg_duration(runbook_id: str):
    """GET /runbooks/{runbook_id}/average-duration"""
    r = _S.get(f"{API}/runbooks/{runbook_id}/average-duration", timeout=8, verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json().get("data", {}).get("average_duration")

def get_recent_runbook_executions():
    """GET /runbooks/executions/recent"""
    r = _S.get(f"{API}/runbooks/executions/recent", timeout=10, verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json().get("data", [])

def extract_rca_from_incident(incident: dict):
    """
    Return the RCA info embedded in an incident payload.
    Tries common keys and shapes; returns None if nothing usable.
    """
    if not incident or not isinstance(incident, dict):
        return None

    # Common direct keys
    for k in ("rca", "rca_analysis", "rcaReport", "rca_report", "latest_rca"):
        if k in incident and incident[k]:
            return incident[k]

    # Sometimes nested under a list or object
    for k in ("rca_list", "rcas", "analyses", "analysis"):
        v = incident.get(k)
        if isinstance(v, list) and v:
            return v[0]
        if isinstance(v, dict) and v:
            return v

    # Only an ID exists (no endpoint available to resolve)
    for k in ("rca_id", "rcaId", "rca_analysis_id", "rca_report_id"):
        if incident.get(k):
            return {"rca_id": incident[k]}

    return None


def extract_prediction_from_incident(incident: dict):
    """
    Return prediction info embedded in an incident payload.
    Tries common keys and shapes; returns None if nothing usable.
    """
    if not incident or not isinstance(incident, dict):
        return None

    # Direct keys
    for k in ("prediction", "latest_prediction", "forecast", "prediction_output"):
        if k in incident and incident[k]:
            return incident[k]

    # Collections
    for k in ("predictions", "forecasts"):
        v = incident.get(k)
        if isinstance(v, list) and v:
            # choose most recent if timestamps exist
            def _ts(x):
                for tk in ("created_at", "timestamp", "ts", "time", "updated_at"):
                    if isinstance(x, dict) and x.get(tk):
                        return x[tk]
                return ""
            return sorted(v, key=_ts, reverse=True)[0]
        if isinstance(v, dict) and v:
            return v

    # Only an ID exists (no endpoint to resolve)
    for k in ("prediction_id", "forecast_id"):
        if incident.get(k):
            return {"prediction_id": incident[k]}

    return None