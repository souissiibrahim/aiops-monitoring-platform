import os, re, uuid, time, threading, subprocess, sys
from collections import deque
from typing import Dict, List, Optional
from fastapi import APIRouter, Query
import json

router = APIRouter()

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
TERMINAL = {"FINISHED", "FAILED", "CANCELED"}
FLINK_JOBMANAGER_CONTAINER = os.getenv("FLINK_JOBMANAGER_CONTAINER", "flink-jobmanager")
FLINK_BIN_IN_CONTAINER     = os.getenv("FLINK_BIN_IN_CONTAINER", "/opt/flink/bin/flink")
FLINK_PYJOBS_DIR_IN_CONT   = os.getenv("FLINK_PYJOBS_DIR_IN_CONTAINER", "/opt/flink/pyjobs")

KAFKA_CONTAINER            = os.getenv("KAFKA_CONTAINER", "kafka")
KAFKA_BOOTSTRAP            = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

LOG_DIR                    = os.getenv("FLINK_LOG_DIR", "flink_logs")
MAX_CONCURRENT             = int(os.getenv("FLINK_MAX_CONCURRENT", "3"))
os.makedirs(LOG_DIR, exist_ok=True)

FLINK_JOBS: Dict[str, Dict] = {
    "metric_producer": {
        "pyfile": f"{FLINK_PYJOBS_DIR_IN_CONT}/metric_producer_job.py",
        "args": [],
        "job_name": "metric_producer",
    },
    "data_cleaning": {
        "pyfile": f"{FLINK_PYJOBS_DIR_IN_CONT}/data_cleaning_job.py",
        "args": [],
        "job_name": "data_cleaning",
    },
    "anomaly_detection": {
        "pyfile": f"{FLINK_PYJOBS_DIR_IN_CONT}/anomaly_detection_job.py",
        "args": [],
        "job_name": "anomaly_detection",
    },
    "log_cleaner": {
        "pyfile": f"{FLINK_PYJOBS_DIR_IN_CONT}/log_cleaner_job.py",
        "args": [],
        "job_name": "log_cleaner",
    },
}

SCRIPTS: Dict[str, Dict] = {
    "log_poller_to_kafka": {
        "module": "scripts.log_poller_to_kafka",
        "args": [],
        
    },

    "anomaly_kafka_ingester": {
        "module": "scripts.anomaly_kafka_ingester",
        "args": [],
    },

    "expire_predictions": {
        "module": "scripts.expire_predictions",
        "args": [],
    },

    "stream_forecasts_to_kafka": {
        "module": "scripts.stream_forecasts_to_kafka",
        "args": [],
    },

    "predict_incidents_from_forecasts": {
        "module": "scripts.predict_incidents_from_forecasts",
        "args": [],
    },

    "predicted_incidents_to_fastapi": {
        "module": "scripts.predicted_incidents_to_fastapi",
        "args": [],
    },

    "confluence_sync": {
        "module": "app.mcp.mcp_tools.confluence_sync",
        "args": [],
        "env": {
        },
    },


    "jira_sync": {
        "module": "app.mcp.mcp_tools.jira_sync",
        "args": [],
        "env": {
        },
    },


    "slack_sync": {
        "module": "app.mcp.mcp_tools.slack_sync",
        "args": [],
        "env": {
        },
    },


    "rca_agent": {
        "module": "app.coreAgents.Agents.rca_agent",
        "args": [
        ],
        "env": {
        },
    },
}

_JOBS: Dict[str, Dict] = {}    
_ACTIVE: Dict[str, str] = {}   
_LOCK = threading.Lock()

_JOBID_PATTERNS = [
    re.compile(r"JobID:\s*([0-9a-fA-F\-]{8,})"),                                
    re.compile(r"Job has been submitted with JobID\s+([0-9a-fA-F\-]{8,})"),     
    re.compile(r"Job with JobID\s+([0-9a-fA-F\-]{8,})\s+has"),                   
    re.compile(r"Submitted job\s+([0-9a-fA-F\-]{8,})"),                          
]
_JOBID_HEX = re.compile(r"\b([0-9a-fA-F]{32})\b")

def _flink_get_job_state(cluster_job_id: str) -> Optional[str]:
    """
    Ask the JobManager REST API for the job state.
    Returns one of: CREATED, RUNNING, FINISHED, CANCELED, FAILED, RECONCILING, or None if unknown.
    """
    try:
        # Query via REST on the JobManager container
        cmd = [
            "docker", "exec", "-i", FLINK_JOBMANAGER_CONTAINER,
            "bash", "-lc",
            f"curl -s http:/adress_loc/:8081/jobs/{cluster_job_id}"
        ]
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8  )
        if out.returncode != 0 or not out.stdout:
            return None
        data = json.loads(out.stdout)
        # Flink 1.17 returns {"state":"RUNNING", ...}
        return data.get("state")
    except Exception:
        return None


def _set_local(job_key: str, cluster_job_id: str, status: str, rc: int = 0):
    active_key = f"flink:{job_key}"
    now = int(time.time())
    with _LOCK:
        # latest record for this key/id
        target = None
        for rec in sorted(_JOBS.values(), key=lambda j: j["started_at"], reverse=True):
            if rec.get("active_key") == active_key and rec.get("cluster_job_id") == cluster_job_id:
                target = rec
                break
        if target:
            target["status"] = status
            if status in {"canceled", "failed", "finished"}:
                target["finished_at"] = now
                target["return_code"] = rc
        if status in {"canceled", "failed", "finished"}:
            _ACTIVE.pop(active_key, None)

def _reconcile_flink_job(active_key: str, cluster_job_id: str):
    """
    Sync local _JOBS/_ACTIVE with real Flink job state.
    """
    state = _flink_get_job_state(cluster_job_id)
    if not state:
        return
    finished_states = {"FINISHED", "FAILED", "CANCELED"}
    with _LOCK:
        # find the most recent record for this active_key
        target = None
        for rec in sorted(_JOBS.values(), key=lambda j: j["started_at"], reverse=True):
            if rec.get("active_key") == active_key and rec.get("cluster_job_id") == cluster_job_id:
                target = rec
                break
        if not target:
            return
        if state in finished_states:
            target["status"] = state.lower()  # "finished"/"failed"/"canceled"
            target["finished_at"] = int(time.time())
            target["return_code"] = 0 if state != "FAILED" else 1
            _ACTIVE.pop(active_key, None)
        elif state == "RUNNING":
            target["status"] = "running"

def _try_parse_cluster_job_id(text: str) -> Optional[str]:
    for pat in _JOBID_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1)
    return None

def _venv_env(base_env: dict) -> dict:
    env = base_env.copy()
    venv_bin = os.path.dirname(sys.executable)
    venv_dir = os.path.dirname(venv_bin)
    env["VIRTUAL_ENV"] = venv_dir
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = PROJECT_ROOT + (os.pathsep + env.get("PYTHONPATH", ""))
    env.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    return env

def _write_header(log_path: str, header: Dict):
    with open(log_path, "a", encoding="utf-8") as f:
        for k, v in header.items():
            f.write(f"[runner] {k}={v}\n")

def _tail_reader(proc: subprocess.Popen, log_path: str, logs_tail: deque, job_id: str, parse_jobid: bool = False):
    try:
        with open(log_path, "a", buffering=1, encoding="utf-8", errors="ignore") as f:
            while True:
                if proc.poll() is not None:
                    for stream in (proc.stdout, proc.stderr):
                        if stream:
                            line = stream.readline()
                            while line:
                                s = line if isinstance(line, str) else line.decode("utf-8", "ignore")
                                f.write(s)
                                logs_tail.append(s.strip())
                                if parse_jobid:
                                    jid = _try_parse_cluster_job_id(s)
                                    if jid:
                                        with _LOCK:
                                            job = _JOBS.get(job_id)
                                            if job and not job.get("cluster_job_id"):
                                                job["cluster_job_id"] = jid
                                line = stream.readline()
                    break

                out = proc.stdout.readline() if proc.stdout else b""
                if out:
                    s = out if isinstance(out, str) else out.decode("utf-8", "ignore")
                    f.write(s)
                    logs_tail.append(s.strip())
                    if parse_jobid:
                        jid = _try_parse_cluster_job_id(s)
                        if jid:
                            with _LOCK:
                                job = _JOBS.get(job_id)
                                if job and not job.get("cluster_job_id"):
                                    job["cluster_job_id"] = jid

                err = proc.stderr.readline() if proc.stderr else b""
                if err:
                    s = err if isinstance(err, str) else err.decode("utf-8", "ignore")
                    f.write(s)
                    logs_tail.append(s.strip())

                time.sleep(0.05)
    except Exception as e:
        with _LOCK:
            job = _JOBS.get(job_id)
            if job:
                job["error"] = f"log_tail_error:{e}"

def _monitor(job_id: str, proc: subprocess.Popen, active_key: str):
    rc = proc.wait()
    finished = int(time.time())
    is_flink = active_key.startswith("flink:")

    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            _ACTIVE.pop(active_key, None)
            return

        if is_flink:
            if rc == 0:
                job["status"] = "running"
                job["return_code"] = None  
                job["finished_at"] = None
               
            else:
                
                job["return_code"] = rc
                job["finished_at"] = finished
                job["status"] = "failed"
                _ACTIVE.pop(active_key, None)
        else:
        
            job["return_code"] = rc
            job["finished_at"] = finished
            job["status"] = "succeeded" if rc == 0 else "failed"
            _ACTIVE.pop(active_key, None)

def _build_flink_run_cmd(pyfile_in_container: str, extra_args: List[str], job_name: Optional[str] = None) -> List[str]:
    """
    docker exec -i flink-jobmanager /opt/flink/bin/flink run -py <pyfile> -d -yD pipeline.name=<name> <args...>
    """
    base = [
        "docker", "exec", "-i", FLINK_JOBMANAGER_CONTAINER,
        FLINK_BIN_IN_CONTAINER, "run",
        "-py", pyfile_in_container,
        "-d",
    ]
    if job_name:
        base += ["-yD", f"pipeline.name={job_name}"]
    return base + extra_args

def _build_flink_cancel_cmd(cluster_job_id: str) -> List[str]:
    return [
        "docker", "exec", "-i", FLINK_JOBMANAGER_CONTAINER,
        FLINK_BIN_IN_CONTAINER, "cancel", cluster_job_id
    ]

def _build_flink_list_cmd() -> List[str]:
    return ["docker", "exec", "-i", FLINK_JOBMANAGER_CONTAINER, FLINK_BIN_IN_CONTAINER, "list", "-a"]

def _build_kafka_consumer_cmd(topic: str, from_beginning: bool = True, group: Optional[str] = None) -> List[str]:
    cmd = [
        "docker", "exec", "-i", KAFKA_CONTAINER,
        "kafka-console-consumer",
        "--bootstrap-server", KAFKA_BOOTSTRAP,
        "--topic", topic
    ]
    if from_beginning:
        cmd.append("--from-beginning")
    if group:
        cmd += ["--group", group]
    return cmd

def _build_python_script_cmd(module: str, extra_args: List[str], env_overrides: Optional[Dict[str, str]] = None) -> (List[str], dict):
    """
    Build a command to run a local Python module inside the current venv:
      <sys.executable> -m <module> <args...>
    Returns (cmd, env) where env merges base venv env + overrides.
    """
    cmd = [sys.executable, "-m", module, *extra_args]
    env = _venv_env(os.environ)
    if env_overrides:
        env.update(env_overrides)
    return cmd, env

def _resolve_cluster_job_id_from_list(job_name: str) -> Optional[str]:
    """
    Run `flink list -a` in the JobManager and try to resolve JobID by job_name.
    """
    cmd = ["docker", "exec", "-i", FLINK_JOBMANAGER_CONTAINER,
           FLINK_BIN_IN_CONTAINER, "list", "-a"]
    out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in (out.stdout or "").splitlines():
        if job_name in line:
            m = re.search(r"\b([0-9a-fA-F]{32})\b", line)
            if m:
                return m.group(1)
    return None

def _start_proc(cmd: List[str], log_path: str, active_key: str, parse_jobid: bool = False) -> dict:
    env = _venv_env(os.environ)

    with _LOCK:
        if active_key in _ACTIVE:
            existing = _ACTIVE[active_key]
            return {"ok": True, "job_id": existing, "status": "running", "info": "already_running"}

        running = sum(1 for j in _JOBS.values() if j["status"] == "running")
        if running >= MAX_CONCURRENT:
            return {"ok": False, "error": "concurrency_limit", "limit": MAX_CONCURRENT}

        job_id = str(uuid.uuid4())
        header = {
            "cmd": " ".join(cmd),
            "sys.executable": sys.executable,
            "cwd": PROJECT_ROOT,
            "VIRTUAL_ENV": env.get("VIRTUAL_ENV", ""),
            "PATH": env.get("PATH", ""),
            "PYTHONPATH": env.get("PYTHONPATH", ""),
        }
        _write_header(log_path, header)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            bufsize=1,
            cwd=PROJECT_ROOT, 
            env=env,
        )

        started = int(time.time())
        logs_tail = deque(maxlen=300) 
        _JOBS[job_id] = {
            "job_id": job_id,
            "active_key": active_key,
            "cmd": cmd,
            "pid": proc.pid,
            "status": "running",
            "started_at": started,
            "finished_at": None,
            "return_code": None,
            "log_path": log_path,
            "logs_tail": logs_tail,
            "error": None,
            "cluster_job_id": None,
        }
        _ACTIVE[active_key] = job_id

        threading.Thread(target=_tail_reader, args=(proc, log_path, logs_tail, job_id, parse_jobid), daemon=True).start()
        threading.Thread(target=_monitor, args=(job_id, proc, active_key), daemon=True).start()

        return {"ok": True, "job_id": job_id, "status": "running"}

def _serialize(job: dict) -> dict:
    return {
        "job_id": job["job_id"],
        "key": job["active_key"],
        "pid": job["pid"],
        "status": job["status"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "return_code": job["return_code"],
        "log_path": job["log_path"],
        "logs_tail": list(job["logs_tail"]),
        "error": job["error"],
        "cluster_job_id": job.get("cluster_job_id"),
    }

@router.post("/flink/{job_key}/start", tags=["running"])
def start_flink_job(job_key: str):
    """
    Starts a Flink job inside the Flink JobManager container via:
      docker exec -i <FLINK_JOBMANAGER_CONTAINER> flink run --jobName <name> -d -py <pyfile>
    Also schedules a short delayed resolver that uses `flink list -a` to backfill
    cluster_job_id if stdout parsing didn't catch it.
    """
    cfg = FLINK_JOBS.get(job_key)
    if not cfg:
        return {"ok": False, "error": f"unknown_job:{job_key}"}

    pyfile = cfg["pyfile"]
    extra_args = cfg.get("args", [])
    job_name = cfg.get("job_name", job_key)

    cmd = _build_flink_run_cmd(pyfile, extra_args, job_name=job_name)
    log_path = os.path.join(LOG_DIR, f"{job_key}_{uuid.uuid4()}.log")

    resp = _start_proc(cmd, log_path, active_key=f"flink:{job_key}", parse_jobid=True)

    def _resolve_later():
        time.sleep(2)
        #_resolve_cluster_job_id_from_list(job_key, job_name)
        _resolve_cluster_job_id_from_list(job_name)

    threading.Thread(target=_resolve_later, daemon=True).start()
    return resp

@router.post("/flink/{job_key}/cancel", tags=["running"])
def cancel_flink_job(job_key: str):
    cfg = FLINK_JOBS.get(job_key)
    if not cfg:
        return {"ok": False, "error": f"unknown_job:{job_key}"}
    job_name = cfg.get("job_name", job_key)
    active_key = f"flink:{job_key}"

    # 1) find cluster_job_id
    with _LOCK:
        job_id = _ACTIVE.get(active_key)
        job = _JOBS.get(job_id) if job_id else None
        cluster_job_id = (job or {}).get("cluster_job_id")

    latest = None
    if not cluster_job_id:
        with _LOCK:
            for rec in sorted(_JOBS.values(), key=lambda j: j["started_at"], reverse=True):
                if rec.get("active_key") == active_key and rec.get("cluster_job_id"):
                    latest = rec
                    break
        if latest:
            cluster_job_id = latest["cluster_job_id"]

    if not cluster_job_id:
        cluster_job_id = _resolve_cluster_job_id_from_list(job_name)
    if not cluster_job_id:
        return {"ok": False, "error": "cluster_job_id_unknown"}

    # 2) issue cancel
    cancel_cmd = _build_flink_cancel_cmd(cluster_job_id)
    out = subprocess.run(cancel_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # 3) poll REST up to ~5s for terminal state
    noted_state = None
    if out.returncode == 0:
        # optimistic local flip to "canceled" to avoid UI showing "running"
        _set_local(job_key, cluster_job_id, "canceled", rc=0)

        deadline = time.time() + 5.0
        while time.time() < deadline:
            st = _flink_get_job_state(cluster_job_id)
            if st:
                noted_state = st
                if st in TERMINAL:
                    # normalize and finalize local state precisely
                    if st == "CANCELED":
                        _set_local(job_key, cluster_job_id, "canceled", rc=0)
                    elif st == "FAILED":
                        _set_local(job_key, cluster_job_id, "failed", rc=1)
                    else:
                        _set_local(job_key, cluster_job_id, "finished", rc=0)
                    break
            time.sleep(0.25)
    else:
        # cancel command failed; still try to reconcile
        st = _flink_get_job_state(cluster_job_id)
        noted_state = st
        if st in TERMINAL:
            if st == "CANCELED":
                _set_local(job_key, cluster_job_id, "canceled", rc=0)
            elif st == "FAILED":
                _set_local(job_key, cluster_job_id, "failed", rc=1)
            else:
                _set_local(job_key, cluster_job_id, "finished", rc=0)

    # 4) read back local status for response
    with _LOCK:
        status = None
        for rec in sorted(_JOBS.values(), key=lambda j: j["started_at"], reverse=True):
            if rec.get("active_key") == active_key and rec.get("cluster_job_id") == cluster_job_id:
                status = rec.get("status")
                break

    combined = (out.stderr or "") + (out.stdout or "")
    already_terminal = (
        "already reached another terminal state" in combined
        or "is not running" in combined
        or (noted_state in TERMINAL)
        or (status in {"canceled", "failed", "finished"})
    )

    return {
        "ok": True if (out.returncode == 0 or already_terminal) else False,
        "cluster_job_id": cluster_job_id,
        "status_after_reconcile": status,
        "observed_flink_state": noted_state,
        "cancel_cmd": " ".join(cancel_cmd),
        "stdout": out.stdout,
        "stderr": out.stderr,
        "note": (
            "transition detected and synced"
            if status in {"canceled", "failed", "finished"}
            else "cancel acknowledged; waiting for REST to flip"
        ),
    }

@router.post("/flink/{job_key}/kill-client", tags=["running"])
def kill_flink_client(job_key: str):
    """
    Kills the local 'docker exec ... flink run' client process (not recommended; use cancel).
    """
    with _LOCK:
        job_id = _ACTIVE.get(f"flink:{job_key}")
        if not job_id:
            return {"ok": False, "error": "not_running"}
        job = _JOBS.get(job_id)
        if not job or not job["pid"] or job["status"] != "running":
            return {"ok": False, "error": "not_running"}
        try:
            os.kill(job["pid"], 15) 
            job["status"] = "stopping"
            return {"ok": True, "status": "stopping"}
        except Exception as e:
            job["error"] = f"kill_failed:{e}"
            return {"ok": False, "error": f"kill_failed:{e}"}

@router.post("/kafka/consume/start", tags=["running"])
def start_kafka_consumer(
    topic: str = Query(..., description="Kafka topic to consume"),
    from_beginning: bool = Query(True, description="Start from earliest"),
    group: Optional[str] = Query(None, description="Optional consumer group"),
):
    active_key = f"kafka:{topic}:{group or ''}"
    cmd = _build_kafka_consumer_cmd(topic=topic, from_beginning=from_beginning, group=group)
    log_path = os.path.join(LOG_DIR, f"kafka_{topic}_{uuid.uuid4()}.log")
    return _start_proc(cmd, log_path, active_key=active_key, parse_jobid=False)

@router.post("/kafka/consume/stop", tags=["running"])
def stop_kafka_consumer(
    topic: str = Query(..., description="Kafka topic"),
    group: Optional[str] = Query(None, description="Optional consumer group"),
):
    active_key = f"kafka:{topic}:{group or ''}"
    with _LOCK:
        job_id = _ACTIVE.get(active_key)
        if not job_id:
            return {"ok": False, "error": "not_running"}
        job = _JOBS.get(job_id)
        if not job or not job["pid"] or job["status"] != "running":
            return {"ok": False, "error": "not_running"}
        try:
            os.kill(job["pid"], 15)
            job["status"] = "stopping"
            return {"ok": True, "status": "stopping"}
        except Exception as e:
            job["error"] = f"stop_failed:{e}"
            return {"ok": False, "error": f"stop_failed:{e}"}

@router.get("/runtime/jobs", tags=["running"])
def list_runtime_jobs():
    with _LOCK:
        items = sorted(_JOBS.values(), key=lambda j: j["started_at"], reverse=True)
        return {"ok": True, "items": [_serialize(j) for j in items]}

@router.get("/runtime/jobs/{job_id}", tags=["running"])
def get_runtime_job(job_id: str):
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "item": _serialize(job)}

@router.get("/flink/list", tags=["running"])
def flink_list_all():
    out = subprocess.run(_build_flink_list_cmd(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return {"ok": True, "stdout": out.stdout, "stderr": out.stderr}


@router.post("/script/{script_key}/start", tags=["running"])
def start_script(script_key: str):
    """
    Start a long-running script (inside this FastAPI venv).
    Singleton per script_key.
    """
    cfg = SCRIPTS.get(script_key)
    if not cfg:
        return {"ok": False, "error": f"unknown_script:{script_key}"}

    module = cfg["module"]
    extra_args = cfg.get("args", [])
    env_overrides = cfg.get("env", {})

    cmd, env = _build_python_script_cmd(module, extra_args, env_overrides)

    log_path = os.path.join(LOG_DIR, f"script_{script_key}_{uuid.uuid4()}.log")

    base_env = _venv_env(os.environ)
    base_env.update(env)

    with _LOCK:
        active_key = f"script:{script_key}"
        if active_key in _ACTIVE:
            existing = _ACTIVE[active_key]
            return {"ok": True, "job_id": existing, "status": "running", "info": "already_running"}

        running = sum(1 for j in _JOBS.values() if j["status"] == "running")
        if running >= MAX_CONCURRENT:
            return {"ok": False, "error": "concurrency_limit", "limit": MAX_CONCURRENT}

        job_id = str(uuid.uuid4())
        header = {
            "cmd": " ".join(cmd),
            "sys.executable": sys.executable,
            "cwd": PROJECT_ROOT,
            "VIRTUAL_ENV": base_env.get("VIRTUAL_ENV", ""),
            "PATH": base_env.get("PATH", ""),
            "PYTHONPATH": base_env.get("PYTHONPATH", ""),
        }
        _write_header(log_path, header)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            bufsize=1,
            cwd=PROJECT_ROOT,
            env=base_env,
        )

        started = int(time.time())
        logs_tail = deque(maxlen=200)
        _JOBS[job_id] = {
            "job_id": job_id,
            "active_key": active_key,
            "cmd": cmd,
            "pid": proc.pid,
            "status": "running",
            "started_at": started,
            "finished_at": None,
            "return_code": None,
            "log_path": log_path,
            "logs_tail": logs_tail,
            "error": None,
            "cluster_job_id": None,
        }
        _ACTIVE[active_key] = job_id

        threading.Thread(target=_tail_reader, args=(proc, log_path, logs_tail, job_id, False), daemon=True).start()
        threading.Thread(target=_monitor, args=(job_id, proc, active_key), daemon=True).start()

        return {"ok": True, "job_id": job_id, "status": "running"}


@router.post("/script/{script_key}/stop", tags=["running"])
def stop_script(script_key: str):
    """
    Gracefully stop a running script (SIGTERM). Falls back to 'not_running' if no PID is active.
    """
    active_key = f"script:{script_key}"
    with _LOCK:
        job_id = _ACTIVE.get(active_key)
        if not job_id:
            return {"ok": False, "error": "not_running"}
        job = _JOBS.get(job_id)
        if not job or not job["pid"] or job["status"] != "running":
            return {"ok": False, "error": "not_running"}
        try:
            os.kill(job["pid"], 15)  
            job["status"] = "stopping"
            return {"ok": True, "status": "stopping"}
        except Exception as e:
            job["error"] = f"stop_failed:{e}"
            return {"ok": False, "error": f"stop_failed:{e}"}