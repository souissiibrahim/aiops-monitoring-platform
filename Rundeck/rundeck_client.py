import os
import requests
from typing import Optional, Dict, Any


RUNDECK_BASE_URL = os.getenv("RUNDECK_BASE_URL", "http://localhost:4440").rstrip("/")
RUNDECK_API_TOKEN = os.getenv("RUNDECK_API_TOKEN", "")
RUNDECK_API_VERSION = os.getenv("RUNDECK_API_VERSION", "45")  # you were using 45 already


class RundeckError(RuntimeError):
    pass


def _headers() -> Dict[str, str]:
    if not RUNDECK_API_TOKEN:
        raise RundeckError("RUNDECK_API_TOKEN is not set")
    return {
        "X-Rundeck-Auth-Token": RUNDECK_API_TOKEN,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _api_url(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return f"{RUNDECK_BASE_URL}/api/{RUNDECK_API_VERSION}{path}"


def _handle_response(r: requests.Response) -> Dict[str, Any]:
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        # Try to surface Rundeck error body for easier debugging
        try:
            err = r.json()
        except Exception:
            err = {"text": r.text}
        raise RundeckError(f"Rundeck HTTP {r.status_code}: {e} | {err}") from e
    try:
        return r.json()
    except ValueError:
        return {"raw": r.text}


def trigger_rundeck_job(job_id: str, argstring: str = "", options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Trigger a Rundeck job and return the execution payload.

    Args:
        job_id: Rundeck job UUID
        argstring: Classic Rundeck argString, e.g. "-incident_id 123 -service web"
        options:   Optional dict to send as 'options' in body (for optionized jobs)

    Returns:
        Dict containing execution info (e.g., {"id": 66, "status": "running", ...})

    Raises:
        RundeckError on HTTP or API error
    """
    url = _api_url(f"/job/{job_id}/run")
    payload: Dict[str, Any] = {}
    if argstring:
        payload["argString"] = argstring
    if options:
        payload["options"] = options

    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    return _handle_response(r)


def get_execution(execution_id: int | str) -> Dict[str, Any]:
    """
    Fetch a Rundeck execution by ID.

    Returns:
        Dict with execution details. Look at 'status' key for values:
        'running' | 'succeeded' | 'failed' | 'aborted' | 'timedout' | ...
    """
    url = _api_url(f"/execution/{execution_id}")
    r = requests.get(url, headers=_headers(), timeout=20)
    return _handle_response(r)


def get_execution_state(execution_id: int | str) -> Dict[str, Any]:
    """
    Fetch live state for an execution (node steps, step states, etc.).
    Useful for finer-grained polling if you need it.
    """
    url = _api_url(f"/execution/{execution_id}/state")
    r = requests.get(url, headers=_headers(), timeout=20)
    return _handle_response(r)


def get_execution_output(execution_id: int | str, lastmod: Optional[int] = None, max_lines: Optional[int] = 200) -> Dict[str, Any]:
    """
    Fetch execution output (logs). Returns JSON with entries.

    Args:
        execution_id: Rundeck execution ID
        lastmod:      Optional lastModified time token (int) for incremental fetch
        max_lines:    Optional max lines per request

    Returns:
        Dict with log entries and paging tokens
    """
    params: Dict[str, Any] = {"format": "json"}
    if lastmod is not None:
        params["lastModified"] = lastmod
    if max_lines is not None:
        params["maxlines"] = max_lines

    url = _api_url(f"/execution/{execution_id}/output")
    r = requests.get(url, headers=_headers(), params=params, timeout=30)
    return _handle_response(r)
