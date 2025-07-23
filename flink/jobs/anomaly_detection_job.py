import os
import json
import numpy as np
import joblib
from datetime import datetime
import tensorflow as tf
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaSink, KafkaRecordSerializationSchema
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.common.watermark_strategy import WatermarkStrategy

# --- Constants ---
MODEL_DIR = "/opt/flink/pyjobs/model"
MODEL_PATH = os.path.join(MODEL_DIR, "autoencoder_model")
THRESHOLD_PATH = os.path.join(MODEL_DIR, "threshold.json")
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.joblib")
FEATURES_PATH = os.path.join(MODEL_DIR, "feature_names.json")
KAFKA_INPUT_TOPIC = "cleaned-metrics"
KAFKA_OUTPUT_TOPIC = "anomalies"
KAFKA_BOOTSTRAP = "kafka:9092"

# --- Load model and preprocessing assets ---
try:
    model = tf.keras.models.load_model(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    with open(THRESHOLD_PATH, "r") as f:
        THRESHOLD = float(json.load(f)["threshold"])
    with open(FEATURES_PATH, "r") as f:
        FEATURE_NAMES = json.load(f)
except Exception as e:
    raise RuntimeError(f"❌ Initialization failed: {e}")

# --- Flink environment ---
env = StreamExecutionEnvironment.get_execution_environment()
env.set_parallelism(1)

# --- Kafka Source ---
source = KafkaSource.builder() \
    .set_bootstrap_servers(KAFKA_BOOTSTRAP) \
    .set_topics(KAFKA_INPUT_TOPIC) \
    .set_group_id("anomaly-detector") \
    .set_value_only_deserializer(SimpleStringSchema()) \
    .build()

# --- Kafka Sink ---
sink = KafkaSink.builder() \
    .set_bootstrap_servers(KAFKA_BOOTSTRAP) \
    .set_record_serializer(
        KafkaRecordSerializationSchema.builder()
        .set_topic(KAFKA_OUTPUT_TOPIC)
        .set_value_serialization_schema(SimpleStringSchema())
        .build()
    ).build()

# --- Anomaly Detection Function ---
def detect_anomaly(json_str):
    try:
        data = json.loads(json_str)

        # Build feature vector with correct order, default to 0.0
        raw_features = [data.get(metric, 0.0) for metric in FEATURE_NAMES]
        scaled_features = scaler.transform([raw_features])

        # Predict reconstruction and compute MSE loss
        reconstruction = model.predict(scaled_features, verbose=0)
        loss = float(np.mean(np.square(scaled_features - reconstruction)))

        # Annotate result
        data["anomaly_score"] = loss
        data["is_anomaly"] = loss > THRESHOLD
        data["detected_at"] = datetime.utcnow().isoformat()

        return json.dumps(data)

    except Exception as e:
        return json.dumps({
            "error": str(e),
            "raw": json_str,
            "detected_at": datetime.utcnow().isoformat()
        })

# --- Build pipeline ---
ds = env.from_source(
    source,
    watermark_strategy=WatermarkStrategy.for_monotonous_timestamps(),
    source_name="KafkaSource"
)

ds = ds.map(detect_anomaly, output_type=Types.STRING())
ds.sink_to(sink)

# --- Execute Flink Job ---
env.execute("Real-Time Anomaly Detection with AutoEncoder")
