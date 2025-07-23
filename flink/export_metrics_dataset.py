import json
import csv
import os
from kafka import KafkaConsumer

# ------------------ Configuration ------------------
KAFKA_TOPIC = "cleaned-metrics"
KAFKA_SERVER = "localhost:29092"  # External port from Docker
CSV_FILE = os.path.join("cleanCSV", "cleaned_historical_metrics.csv")

# ------------------ Ensure output directory --------
os.makedirs("cleanCSV", exist_ok=True)

# ------------------ Initialize CSV file ------------
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "metric_name", "value", "collection_delay", "confidence"])
    print("📄 Initialized cleaned CSV file.")

# ------------------ Kafka Consumer -----------------
consumer = KafkaConsumer(
    KAFKA_TOPIC,
    bootstrap_servers=KAFKA_SERVER,
    auto_offset_reset='earliest',
    group_id="cleaned-metric-exporter-V5",
    enable_auto_commit=True,
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

print("✅ Listening to cleaned-metrics topic...\n")

# ------------------ Deduplication Cache ------------
seen = set()

# ------------------ Message Loop -------------------
for msg in consumer:
    try:
        data = msg.value
        metric_name = data.get("metric_name")
        timestamp = data.get("timestamp")
        value = data.get("value")
        delay = data.get("collection_delay")
        confidence = data.get("confidence")

        if None in (metric_name, timestamp, value):
            print("⚠️ Incomplete record skipped:", data)
            continue

        # Deduplicate by key
        key = f"{metric_name}:{timestamp}:{value}"
        if key in seen:
            continue
        seen.add(key)

        print(f"📥 Writing: {metric_name} @ {timestamp} = {value} (delay={delay}, conf={confidence})")

        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, metric_name, value, delay, confidence])

    except Exception as e:
        print("❌ Error processing message:", e)
