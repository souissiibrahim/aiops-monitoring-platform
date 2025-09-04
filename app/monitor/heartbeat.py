import json, os, time, threading, datetime as dt

HEARTBEAT_BUS = os.getenv("HEARTBEAT_BUS", "queue_incident.jsonl") 

def emit_heartbeat(source: str, **payload):
    msg = {
        "type": "heartbeat",
        "source": source,
        "ts": dt.datetime.utcnow().isoformat() + "Z",
        "payload": payload,
    }
    with open(HEARTBEAT_BUS, "a") as f:
        f.write(json.dumps(msg) + "\n")

def start_heartbeat(source: str, interval_s: int = 30, **static_payload):
    alive = {"running": True}
    def _loop():
        start = time.time()
        while alive["running"]:
            uptime = int(time.time() - start)
            emit_heartbeat(source, uptime_s=uptime, **static_payload)
            time.sleep(interval_s)
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return alive 