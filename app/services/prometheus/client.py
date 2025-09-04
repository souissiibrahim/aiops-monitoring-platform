import requests, math, re

PROM_URL = "http://172.24.68.64:9090"
VERIFY_SSL = True
TIMEOUT = 5


EXCLUDE_DEV_RE = r"lo|docker.*|veth.*|br-.*|cni.*|tun.*|tap.*|virbr.*|wg.*|nm-.*|podman.*"

def _check_ok(resp_json):
    if resp_json.get("status") != "success":
        raise RuntimeError(f"Prom error: {resp_json}")

def _scalar_vector_value(resp_json):
    _check_ok(resp_json)
    data = resp_json["data"]
    result_type = data.get("resultType")
    result = data.get("result", [])
    if result_type == "vector" and result:
        return float(result[0]["value"][1])
    if result_type == "scalar" and data.get("result"):
        return float(data["result"][1])
    return math.nan

def _vector_aggregate(resp_json, agg: str = "sum") -> float:
    """Aggregate all vector values with sum or max."""
    _check_ok(resp_json)
    vals = []
    for r in resp_json.get("data", {}).get("result", []):
        try:
            vals.append(float(r["value"][1]))
        except Exception:
            pass
    if not vals:
        return math.nan
    if agg == "max":
        return max(vals)
    return sum(vals)

def _get(query: str):
    r = requests.get(
        f"{PROM_URL}/api/v1/query",
        params={"query": query},
        timeout=TIMEOUT,
        verify=VERIFY_SSL,
    )
    r.raise_for_status()
    return r.json()

def prom_instant(query: str) -> float:
    return _scalar_vector_value(_get(query))


def current_cpu_pct(instance: str) -> float:
    q = f'100*(1 - avg by(instance)(rate(node_cpu_seconds_total{{mode="idle",instance="{instance}"}}[5m])))'
    v = prom_instant(q)
    return round(v, 2) if not math.isnan(v) else 0.0

def current_mem_pct(instance: str) -> float:
    q = f'100*(1 - node_memory_MemAvailable_bytes{{instance="{instance}"}} / node_memory_MemTotal_bytes{{instance="{instance}"}})'
    v = prom_instant(q)
    return round(v, 2) if not math.isnan(v) else 0.0

def current_disk_pct(instance: str, mountpoint: str = "/") -> float:
   
    q_root = (
        '100*(1 - (node_filesystem_avail_bytes{instance="%s",mountpoint="%s",fstype!~"tmpfs|overlay|squashfs|tracefs|proc|sysfs"}'
        ' / node_filesystem_size_bytes{instance="%s",mountpoint="%s",fstype!~"tmpfs|overlay|squashfs|tracefs|proc|sysfs"}))'
        % (instance, mountpoint, instance, mountpoint)
    )
    v = prom_instant(q_root)
    if not math.isnan(v):
        return round(v, 2)

   
    q_any = (
        '100*(1 - (node_filesystem_avail_bytes{instance="%s",fstype!~"tmpfs|overlay|squashfs|tracefs|proc|sysfs"}'
        ' / node_filesystem_size_bytes{instance="%s",fstype!~"tmpfs|overlay|squashfs|tracefs|proc|sysfs"}))'
        % (instance, instance)
    )
    json_any = _get(q_any)
    mx = _vector_aggregate(json_any, agg="max")
    return round(mx, 2) if not math.isnan(mx) else 0.0


def current_network_mbps(instance: str) -> float:
    """
    Aggregate RX+TX throughput (Mbps) across real NICs.
    Returns 0.00 if no data.
    """
    dev_excl = EXCLUDE_DEV_RE
    q = (
        '8 * sum by(instance) ('
        f'rate(node_network_receive_bytes_total{{instance="{instance}",device!~"{dev_excl}"}}[5m]) + '
        f'rate(node_network_transmit_bytes_total{{instance="{instance}",device!~"{dev_excl}"}}[5m])'
        ') / 1e6'
    )
    v = prom_instant(q)
    return round(v, 2) if not math.isnan(v) else 0.0

def current_network_util_pct(instance: str, link_speed_bps: float | None = None) -> float:
    """
    Utilization % = (RX+TX rate) / link speed * 100.
    If link_speed_bps is None, we sum node_network_speed_bytes across included devices.
    Falls back to Mbps if speed not available (returns 0.0 in that case).
    """
    dev_excl = EXCLUDE_DEV_RE

   
    q_rate = (
        'sum by(instance) ('
        f'rate(node_network_receive_bytes_total{{instance="{instance}",device!~"{dev_excl}"}}[5m]) + '
        f'rate(node_network_transmit_bytes_total{{instance="{instance}",device!~"{dev_excl}"}}[5m])'
        ')'
    )
    rate_bps = prom_instant(q_rate)
    if math.isnan(rate_bps) or rate_bps <= 0:
        return 0.0

    
    if link_speed_bps is None:
        q_speed = f'sum by(instance) (node_network_speed_bytes{{instance="{instance}",device!~"{dev_excl}"}})'
        speed = prom_instant(q_speed)
    else:
        speed = float(link_speed_bps)

    if math.isnan(speed) or speed <= 0:
        return 0.0

    util = (rate_bps / speed) * 100.0
    return round(util, 2)

def uptime_seconds(instance: str) -> int:
    """
    Returns host uptime in seconds using node_exporter:
      time() - node_boot_time_seconds{instance=...}
    """
    q = f'time() - node_boot_time_seconds{{instance="{instance}"}}'
    v = prom_instant(q)
    try:
        return int(v) if not math.isnan(v) else 0
    except Exception:
        return 0