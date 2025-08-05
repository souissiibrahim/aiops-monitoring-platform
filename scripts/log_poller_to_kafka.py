import time
import json
import requests
from datetime import datetime, timedelta
from kafka import KafkaProducer
import re

# --- Configuration ---
LOKI_URL = "http://172.24.68.64:3100/loki/api/v1/query_range"
QUERY = '{job="varlogs"}'  # Adjust to match your Promtail config
WINDOW_SECONDS = 1
POLL_INTERVAL = 1  # seconds
KAFKA_BOOTSTRAP = "localhost:29092"
KAFKA_TOPIC = "logs-streamed"

# --- Strip ANSI color escape codes ---
def strip_ansi(text):
    return re.sub(r'\x1b\[[0-9;]*m', '', text)

# --- Main polling loop ---
def main():
    last_fetch_time = datetime.utcnow() - timedelta(seconds=WINDOW_SECONDS)

    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: v.encode("utf-8")
        )
    except Exception as e:
        print(f"❌ Failed to connect to Kafka: {e}")
        return

    print(f"✅ Starting Loki log polling every {POLL_INTERVAL}s...\n")

    while True:
        try:
            now = datetime.utcnow()
            if now <= last_fetch_time:
                now = last_fetch_time + timedelta(milliseconds=1)

            start_ns = int(last_fetch_time.timestamp() * 1e9)
            end_ns = int(now.timestamp() * 1e9)

            print(f"📡 Querying logs from {last_fetch_time.isoformat()} to {now.isoformat()}")

            response = requests.get(LOKI_URL, params={
                "query": QUERY,
                "start": str(start_ns),
                "end": str(end_ns),
                "limit": "100"
            })

            response.raise_for_status()
            data = response.json()

            streams = data.get("data", {}).get("result", [])
            if not streams:
                print("⚠️  No logs in this window.\n")

            sent_count = 0
            for stream in streams:
                for ts, log_line in stream.get("values", []):
                    clean_log = strip_ansi(log_line)
                    record = json.dumps({
                        "timestamp": ts,
                        "log": clean_log
                    })
                    producer.send(KAFKA_TOPIC, value=record)
                    sent_count += 1

            if sent_count > 0:
                print(f"📤 Sent {sent_count} logs to Kafka ✅\n")

            last_fetch_time = now
            time.sleep(POLL_INTERVAL)

        except requests.exceptions.RequestException as e:
            print(f"❌ Loki query error: {e}\n")
            time.sleep(POLL_INTERVAL)

        except Exception as e:
            error_msg = json.dumps({"error": str(e)})
            try:
                producer.send(KAFKA_TOPIC, value=error_msg)
            except:
                print("❌ Failed to send error to Kafka.")
            print(f"❌ Unexpected error: {e}\n")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
