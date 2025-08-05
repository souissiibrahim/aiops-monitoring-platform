import json
import re
from datetime import datetime
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaSink, KafkaRecordSerializationSchema
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.common.watermark_strategy import WatermarkStrategy

# --- Kafka Topics ---
KAFKA_INPUT_TOPIC = "logs-streamed"
KAFKA_OUTPUT_TOPIC = "logs-cleaned"
KAFKA_BOOTSTRAP = "kafka:9092"

# --- Regex for metadata extraction ---
LEVEL_REGEX = re.compile(r'\b(INFO|DEBUG|WARNING|ERROR|CRITICAL)\b', re.IGNORECASE)
ANSI_REGEX = re.compile(r'\x1b\[[0-9;]*m')

# --- Clean & parse each raw log ---
def clean_log(raw_str):
    try:
        data = json.loads(raw_str)
        log_line = data.get("log", "")

        # Strip ANSI
        log_clean = ANSI_REGEX.sub('', log_line)

        # Extract metadata
        level_match = LEVEL_REGEX.search(log_clean)
        level = level_match.group(0).upper() if level_match else "INFO"

        service_match = re.search(r'(?P<svc>[\w\-]+)\[\d+\]:', log_clean)
        service = service_match.group("svc") if service_match else "unknown"

        # Extract timestamp
        ts_match = re.search(r'^(\d{4}-\d{2}-\d{2}T[\d:.+-Z]+)', log_clean)
        ts = ts_match.group(1) if ts_match else datetime.utcnow().isoformat()

        # Trim message
        message_part = log_clean.split("]:", 1)
        message = message_part[1].strip() if len(message_part) > 1 else log_clean

        return json.dumps({
            "timestamp": ts,
            "level": level,
            "service_name": service,
            "message": message
        })

    except Exception as e:
        return json.dumps({
            "error": str(e),
            "raw": raw_str,
            "detected_at": datetime.utcnow().isoformat()
        })

# --- Flink Job ---
def main():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    source = KafkaSource.builder() \
        .set_bootstrap_servers(KAFKA_BOOTSTRAP) \
        .set_topics(KAFKA_INPUT_TOPIC) \
        .set_group_id("log-cleaner") \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()

    sink = KafkaSink.builder() \
        .set_bootstrap_servers(KAFKA_BOOTSTRAP) \
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(KAFKA_OUTPUT_TOPIC)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        ).build()

    ds = env.from_source(
        source,
        watermark_strategy=WatermarkStrategy.for_monotonous_timestamps(),
        source_name="KafkaSource"
    )

    ds = ds.map(clean_log, output_type=Types.STRING())
    ds.sink_to(sink)

    env.execute("Real-Time Log Cleaning Job")

if __name__ == "__main__":
    main()
