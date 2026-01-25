import time
import json
import requests
from datetime import datetime, timedelta

from pyflink.datastream import StreamExecutionEnvironment, SourceFunction
from pyflink.common.typeinfo import Types
from kafka import KafkaProducer
#from app.monitor.heartbeat import start_heartbeat

#hb = start_heartbeat("log_streamer_job.py", interval_s=20, version="1.0")

# --- Config ---
LOKI_URL = "http://adress_loc:3100/loki/api/v1/query_range"
QUERY = '{job="varlogs"}'  # Adjust based on your Promtail config
WINDOW_SECONDS = 1           # Poll every second for near real-time streaming
KAFKA_TOPIC = "logs-streamed"
KAFKA_BOOTSTRAP = "kafka:9092"

# --- Utility to clean ANSI escape codes ---
def strip_ansi(text):
    import re
    return re.sub(r'\x1b\[[0-9;]*m', '', text)

# --- Custom Source Function to pull from Loki ---
class LokiLogSource(SourceFunction):
    def run(self, ctx):
        last_fetch_time = datetime.utcnow() - timedelta(seconds=WINDOW_SECONDS)

        while True:
            now = datetime.utcnow()
            start_ns = int(last_fetch_time.timestamp() * 1e9)
            end_ns = int(now.timestamp() * 1e9)

            try:
                resp = requests.get(LOKI_URL, params={
                    "query": QUERY,
                    "start": str(start_ns),
                    "end": str(end_ns),
                    "limit": "100"
                })
                data = resp.json()

                for stream in data.get("data", {}).get("result", []):
                    for ts, log_line in stream.get("values", []):
                        log = strip_ansi(log_line)
                        ctx.collect(json.dumps({
                            "timestamp": ts,
                            "log": log
                        }))

            except Exception as e:
                ctx.collect(json.dumps({"error": str(e)}))

            last_fetch_time = now
            time.sleep(WINDOW_SECONDS)

    def cancel(self):
        pass

# --- Flink Main Job ---
def main():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    # Source: Loki
    ds = env.add_source(LokiLogSource()).name("LokiLogSource").set_parallelism(1)

    # Kafka Sink
    def send_to_kafka(record):
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: v.encode("utf-8")
        )
        producer.send(KAFKA_TOPIC, value=record)
        producer.flush()
        producer.close()

    ds.map(send_to_kafka, output_type=Types.STRING())
    env.execute("Loki Log Streamer to Kafka")

if __name__ == "__main__":
    main()
