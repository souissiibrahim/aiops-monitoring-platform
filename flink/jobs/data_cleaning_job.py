import json
import time
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.common.typeinfo import Types
from pyflink.datastream.connectors import FlinkKafkaConsumer
from pyflink.common.serialization import SimpleStringSchema
from kafka import KafkaProducer

# ---------------------- Kafka Config --------------------------
KAFKA_SERVERS = 'kafka:9092'
INPUT_TOPIC = 'prometheus-metrics'
OUTPUT_TOPIC = 'cleaned-metrics'

# ---------------------- Metric Filtering -----------------------

# 🔹 Full match: exact metric names
FULL_MATCH_METRICS = [
    "node_cpu_seconds_total",
    "container_cpu_usage_seconds_total",
    "container_memory_usage_bytes",
    "container_memory_max_usage_bytes",
    "container_threads",
    "container_blkio_device_usage_total",
    "cadvisor_version_info"
]

# 🔹 Prefix match: match any metric that starts with one of these
PREFIX_MATCH_METRICS = [
    "node_memory_",
    "node_disk_",
    "container_fs_usage_bytes",
    "node_network_",
    "container_network_receive_bytes_total",
    "container_network_transmit_bytes_total",
    "container_network_receive_errors_total",
    "container_network_transmit_errors_total",
    "container_network_receive_packets_total",
    "container_network_transmit_packets_total",
    "container_network_receive_packets_dropped_total",
    "container_network_transmit_packets_dropped_total"
]

# ❌ Ignore metrics with these prefixes
IGNORED_PREFIXES = [
    "prometheus_",
    "go_",
    "process_",
    "up",
    "scrape_",
    "container_spec_",
    "container_last_seen"
]

# 🔎 Metric relevance filter
def is_metric_relevant(metric_name: str) -> bool:
    if any(metric_name.startswith(prefix) for prefix in IGNORED_PREFIXES):
        return False
    if metric_name in FULL_MATCH_METRICS:
        return True
    return any(metric_name.startswith(prefix) for prefix in PREFIX_MATCH_METRICS)

# 🧠 Deduplication cache (approximate, per job lifetime)
seen_keys = set()

# ------------------ Flink Environment --------------------------
env = StreamExecutionEnvironment.get_execution_environment()
env.set_parallelism(1)

consumer_props = {
    'bootstrap.servers': KAFKA_SERVERS,
    'group.id': 'flink-cleaner'
}

source = FlinkKafkaConsumer(INPUT_TOPIC, SimpleStringSchema(), consumer_props)
stream = env.add_source(source)

# ------------------ Step 1: Parse & Clean ------------------------
def parse_and_clean(record):
    try:
        print("📥 Raw record received:", record)
        data = json.loads(record)
        name = data["metric_name"]
        value = data["data"]["value"]
        timestamp = float(value[0])
        val = float(value[1])

        print(f"🧪 Parsed: {name} @ {timestamp} = {val}")

        if not is_metric_relevant(name):
            print("🚫 Ignored by relevance filter:", name)
            return None

        if val < 0 or (name.startswith("node_cpu") and val > 100):
            print("⚠️ Filtered by outlier check:", val)
            return None

        key = f"{name}:{timestamp}"
        if key in seen_keys:
            print("🔁 Duplicate skipped:", key)
            return None
        seen_keys.add(key)

        now = time.time()
        delay = round(now - timestamp, 3)
        confidence = 1.0 if val <= 90 and delay <= 10 else 0.6

        print("✅ Cleaned:", name, val)
        return (name, timestamp, val, delay, confidence)

    except Exception as e:
        print("❌ Error parsing:", e)
        return None

# ------------------ Step 2: Filter Valid ------------------------
def is_valid(record):
    return record is not None and record[2] is not None

# ------------------ Step 3: Serialize Cleaned -------------------
def serialize_cleaned(record):
    name, timestamp, val, delay, confidence = record
    return json.dumps({
        "metric_name": name,
        "timestamp": timestamp,
        "value": val,
        "collection_delay": delay,
        "confidence": confidence
    })

# ------------------ Step 4: Send to Kafka -----------------------
def send_to_kafka(clean_record):
    if clean_record is None:
        return
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_SERVERS,
        value_serializer=lambda v: v.encode('utf-8')
    )
    producer.send(OUTPUT_TOPIC, value=clean_record)
    producer.flush()
    producer.close()

# ------------------ Stream Execution ---------------------------
stream \
    .map(parse_and_clean, output_type=Types.TUPLE([
        Types.STRING(),  # metric_name
        Types.FLOAT(),   # timestamp
        Types.FLOAT(),   # value
        Types.FLOAT(),   # delay
        Types.FLOAT()    # confidence
    ])) \
    .filter(is_valid) \
    .map(serialize_cleaned, output_type=Types.STRING()) \
    .map(send_to_kafka)

env.execute("Smart Flink Metric Cleaning Job")
