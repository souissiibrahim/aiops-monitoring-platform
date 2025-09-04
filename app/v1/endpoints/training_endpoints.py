import os, uuid, time, threading, subprocess, sys
from collections import deque
from fastapi import APIRouter

router = APIRouter()
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))

# Only store module names and args; interpreter is resolved at runtime
TRAINER_TEMPLATES = {
    "prophet-cpu":         ("scripts.train_prophet_models", ["--target", "cpu"]),
    "prophet-memory":      ("scripts.train_prophet_models", ["--target", "memory"]),
    "prophet-disk":        ("scripts.train_prophet_models", ["--target", "disk"]),
    "incident-classifier": ("scripts.train_incident_classifier", []),
    "autoencoder":         ("flink.train_autoencoder", []),
}

TRAINING_MAX_CONCURRENT = int(os.getenv("TRAINING_MAX_CONCURRENT", "2"))
TRAINING_LOG_DIR = os.getenv("TRAINING_LOG_DIR", "training_logs")
os.makedirs(TRAINING_LOG_DIR, exist_ok=True)

_JOBS = {}
_ACTIVE_BY_TRAINER = {}
_LOCK = threading.Lock()


def _build_cmd(trainer: str):
    """Build the command for a given trainer using the current interpreter."""
    tmpl = TRAINER_TEMPLATES.get(trainer)
    if not tmpl:
        return None
    module, extra_args = tmpl
    return [sys.executable, "-m", module, *extra_args]


def _venv_env(base_env: dict) -> dict:
    """
    Ensure the child process runs *inside* the same venv as the API worker.
    We set VIRTUAL_ENV and PATH so any nested spawns also use the venv.
    """
    env = base_env.copy()
    venv_bin = os.path.dirname(sys.executable)              # .../venv/bin
    venv_dir = os.path.dirname(venv_bin)                    # .../venv
    env["VIRTUAL_ENV"] = venv_dir
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = PROJECT_ROOT + (os.pathsep + env.get("PYTHONPATH", ""))

    # Optional: reduce TF noise in logs
    env.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    return env


def _tail_reader(proc: subprocess.Popen, log_path: str, logs_tail: deque, job_id: str):
    """Continuously read process output and keep a rolling tail in memory."""
    try:
        with open(log_path, "a", buffering=1, encoding="utf-8", errors="ignore") as f:
            while True:
                if proc.poll() is not None:
                    for stream in (proc.stdout, proc.stderr):
                        if stream:
                            line = stream.readline()
                            while line:
                                try:
                                    s = line if isinstance(line, str) else line.decode("utf-8", "ignore")
                                    f.write(s)
                                    logs_tail.append(s.strip())
                                except Exception:
                                    pass
                                line = stream.readline()
                    break

                line = proc.stdout.readline() if proc.stdout else b""
                if line:
                    try:
                        s = line if isinstance(line, str) else line.decode("utf-8", "ignore")
                        f.write(s)
                        logs_tail.append(s.strip())
                    except Exception:
                        pass

                err = proc.stderr.readline() if proc.stderr else b""
                if err:
                    try:
                        s = err if isinstance(err, str) else err.decode("utf-8", "ignore")
                        f.write(s)
                        logs_tail.append(s.strip())
                    except Exception:
                        pass

                time.sleep(0.05)
    except Exception as e:
        with _LOCK:
            job = _JOBS.get(job_id)
            if job:
                job["error"] = f"log_tail_error: {e}"


def _monitor_job(job_id: str, proc: subprocess.Popen):
    """Wait for process to end; update status & active map."""
    rc = proc.wait()
    finished = int(time.time())
    with _LOCK:
        job = _JOBS.get(job_id)
        if job:
            job["return_code"] = rc
            job["finished_at"] = finished
            job["status"] = "succeeded" if rc == 0 else "failed"
            _ACTIVE_BY_TRAINER.pop(job["trainer"], None)


def _write_log_header(log_path: str, trainer: str, cmd: list, env: dict):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[runner] trainer={trainer}\n")
        f.write(f"[runner] sys.executable={sys.executable}\n")
        f.write(f"[runner] cmd={' '.join(cmd)}\n")
        f.write(f"[runner] cwd={PROJECT_ROOT}\n")
        f.write(f"[runner] VIRTUAL_ENV={env.get('VIRTUAL_ENV','')}\n")
        f.write(f"[runner] PATH={env.get('PATH','')}\n")
        f.write(f"[runner] PYTHONPATH={env.get('PYTHONPATH','')}\n")
        f.write(f"[runner] TF_CPP_MIN_LOG_LEVEL={env.get('TF_CPP_MIN_LOG_LEVEL','')}\n")


def _preflight_tf(log_path: str, env: dict) -> tuple[bool, str | None]:
    """
    Very small subprocess to verify TensorFlow is importable in this environment.
    Uses a multi-line Python snippet to avoid SyntaxError.
    """
    code = """
import sys
print('[preflight] python', sys.executable)
try:
    import tensorflow as tf
    print('[preflight] tensorflow_found', True)
    print('[preflight] tf_version', getattr(tf, '__version__', '?'))
except Exception as e:
    print('[preflight] tensorflow_found', False)
    print('[preflight] import_error', e)
    raise
"""
    pre_cmd = [sys.executable, "-c", code]
    try:
        out = subprocess.run(
            pre_cmd,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(out.stdout or "")
            f.write(out.stderr or "")
        if out.returncode != 0:
            return False, f"preflight_failed_rc={out.returncode}"
        if "tensorflow_found True" not in (out.stdout or ""):
            return False, "preflight_failed_not_found"
        return True, None
    except Exception as e:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[preflight] exception: {e}\n")
        return False, f"preflight_exception:{e}"


def _start_trainer(trainer: str) -> dict:
    cmd = _build_cmd(trainer)
    if not cmd:
        return {"ok": False, "error": f"unknown_trainer:{trainer}"}

    with _LOCK:
        # Avoid duplicate run of the same trainer
        existing_id = _ACTIVE_BY_TRAINER.get(trainer)
        if existing_id:
            return {"ok": True, "job_id": existing_id, "status": "running", "info": "already_running"}

        # Enforce concurrency limit
        active_cnt = sum(1 for j in _JOBS.values() if j["status"] == "running")
        if active_cnt >= TRAINING_MAX_CONCURRENT:
            return {"ok": False, "error": "concurrency_limit", "limit": TRAINING_MAX_CONCURRENT}

        job_id = str(uuid.uuid4())
        log_path = os.path.join(TRAINING_LOG_DIR, f"{trainer}_{job_id}.log")
        env = _venv_env(os.environ)

        _write_log_header(log_path, trainer, cmd, env)

        # Preflight only for trainers that need TF
        if trainer == "autoencoder":
            ok, err = _preflight_tf(log_path, env)
            if not ok:
                started = int(time.time())
                logs_tail = deque(maxlen=50)
                logs_tail.append(f"[preflight] TensorFlow check failed: {err}")
                _JOBS[job_id] = {
                    "job_id": job_id,
                    "trainer": trainer,
                    "cmd": cmd,
                    "pid": None,
                    "status": "failed",
                    "started_at": started,
                    "finished_at": int(time.time()),
                    "return_code": 1,
                    "log_path": log_path,
                    "logs_tail": logs_tail,
                    "error": err,
                }
                return {"ok": True, "job_id": job_id, "status": "failed", "error": err}

        # Launch the real trainer
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
        logs_tail = deque(maxlen=50)
        _JOBS[job_id] = {
            "job_id": job_id,
            "trainer": trainer,
            "cmd": cmd,
            "pid": proc.pid,
            "status": "running",
            "started_at": started,
            "finished_at": None,
            "return_code": None,
            "log_path": log_path,
            "logs_tail": logs_tail,
            "error": None,
        }
        _ACTIVE_BY_TRAINER[trainer] = job_id

        threading.Thread(target=_tail_reader, args=(proc, log_path, logs_tail, job_id), daemon=True).start()
        threading.Thread(target=_monitor_job, args=(job_id, proc), daemon=True).start()

        return {"ok": True, "job_id": job_id, "status": "running"}


def _serialize_job(job: dict) -> dict:
    return {
        "job_id": job["job_id"],
        "trainer": job["trainer"],
        "pid": job["pid"],
        "status": job["status"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "return_code": job["return_code"],
        "log_path": job["log_path"],
        "logs_tail": list(job["logs_tail"]),
        "error": job["error"],
    }


@router.get("/training/jobs", tags=["training"])
def list_training_jobs():
    with _LOCK:
        jobs = sorted(_JOBS.values(), key=lambda j: j["started_at"], reverse=True)
        return {"ok": True, "items": [_serialize_job(j) for j in jobs]}


@router.get("/training/jobs/{job_id}", tags=["training"])
def get_training_job(job_id: str):
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "item": _serialize_job(job)}


@router.post("/training/prophet-cpu/start", tags=["training"])
def start_train_prophet_cpu():
    return _start_trainer("prophet-cpu")


@router.post("/training/prophet-memory/start", tags=["training"])
def start_train_prophet_memory():
    return _start_trainer("prophet-memory")


@router.post("/training/prophet-disk/start", tags=["training"])
def start_train_prophet_disk():
    return _start_trainer("prophet-disk")


@router.post("/training/incident-classifier/start", tags=["training"])
def start_train_incident_classifier():
    return _start_trainer("incident-classifier")


@router.post("/training/autoencoder/start", tags=["training"])
def start_train_autoencoder():
    return _start_trainer("autoencoder")
