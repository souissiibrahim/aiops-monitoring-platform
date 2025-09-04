import os
import json
import time
import numpy as np
import joblib
from datetime import datetime, timezone
import tensorflow as tf
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaSink, KafkaRecordSerializationSchema
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.common.watermark_strategy import WatermarkStrategy

# --- Constants & env ---
MODEL_DIR = "/opt/flink/pyjobs/model"
MODEL_PATH = os.path.join(MODEL_DIR, "autoencoder_model")
THRESHOLD_PATH = os.path.join(MODEL_DIR, "threshold.json")
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.joblib")
ENCODER_PATH = os.path.join(MODEL_DIR, "encoder.joblib")
FEATURES_PATH = os.path.join(MODEL_DIR, "feature_names.json")

KAFKA_INPUT_TOPIC = os.getenv("K_IN", "cleaned-metrics")
KAFKA_OUTPUT_TOPIC = os.getenv("K_OUT", "anomalies")
KAFKA_BOOTSTRAP = os.getenv("K_BOOT", "kafka:9092")

# Decision rules (configurable via env)
N_CONSECUTIVE = int(os.getenv("AE_N_CONSEC", "3"))          # need N points above enter threshold
COOLDOWN_SEC  = int(os.getenv("AE_COOLDOWN_SEC", "300"))    # suppress duplicates for 5 min
MAX_DELAY_SEC = int(os.getenv("AE_MAX_DELAY_SEC", "120"))   # drop points arriving >2 min late

# --- Load model and preprocessing assets ---
try:
    model = tf.keras.models.load_model(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    encoder = joblib.load(ENCODER_PATH)

    # threshold.json can be old (single "threshold") or new (global/by_metric/hysteresis/epsilon)
    with open(THRESHOLD_PATH, "r") as f:
        th_conf = json.load(f)

    if isinstance(th_conf, dict) and ("by_metric" in th_conf or "global" in th_conf):
        GLOBAL_TH = float(th_conf.get("global", th_conf.get("threshold", 1e-6)))
        BY_METRIC = th_conf.get("by_metric", {}) or {}
        EPSILON   = float(th_conf.get("epsilon", 1e-6))
        HYS       = th_conf.get("hysteresis", {"high_pct": 99, "low_pct": 95})
        # enter uses the stored (typically p99), exit slightly lower (p95/p99 ratio)
        EXIT_FACTOR = (HYS.get("low_pct", 95) / HYS.get("high_pct", 99)) if HYS else 0.96
    else:
        # legacy file with only one threshold
        GLOBAL_TH = float(th_conf["threshold"])
        BY_METRIC = {}
        EPSILON   = 1e-6
        EXIT_FACTOR = 0.96

    with open(FEATURES_PATH, "r") as f:
        FEATURE_NAMES = json.load(f)

except Exception as e:
    raise RuntimeError(f"❌ Initialization failed: {e}")

def resolve_threshold(metric_name: str):
    """Return (enter_th, exit_th) for a metric, with epsilon safeguards."""
    base = float(BY_METRIC.get(metric_name, GLOBAL_TH))
    enter_th = max(base, EPSILON)
    exit_th  = max(enter_th * EXIT_FACTOR, EPSILON)
    return enter_th, exit_th

# --- lightweight per-series state (since parallelism=1, process-level dict is OK) ---
# key = (metric_name, instance)
_state = {}  # key -> {"streak": int, "in_alarm": bool, "last_emit": float}

def _get_state(key):
    s = _state.get(key)
    if s is None:
        s = {"streak": 0, "in_alarm": False, "last_emit": 0.0}
        _state[key] = s
    return s

# --- Anomaly Detection Function (keeps the SAME OUTPUT SCHEMA) ---
def detect_anomaly(json_str):
    try:
        data = json.loads(json_str)

        metric_name = str(data.get("metric_name", ""))
        instance    = str(data.get("instance", ""))  # may be empty
        value       = float(data.get("value", 0.0))
        delay       = float(data.get("collection_delay", 0.0))

        # Delay-guard: prefer event timestamp if provided
        now = time.time()
        event_ts = None
        raw_ts = data.get("timestamp")
        if isinstance(raw_ts, (int, float)):
            event_ts = float(raw_ts)
        elif isinstance(raw_ts, str):
            try:
                event_ts = datetime.fromisoformat(raw_ts.replace("Z","+00:00")).timestamp()
            except Exception:
                event_ts = None
        if event_ts is None:
            event_ts = now

        if now - event_ts > MAX_DELAY_SEC:
            # Too late → drop silently by returning the original (non-anomaly) with score only
            # (keep output shape stable; mark normal)
            numeric_features = scaler.transform([[value, delay]])
            categorical_features = encoder.transform([[metric_name]])
            features = np.concatenate([numeric_features, categorical_features], axis=1)
            reconstruction = model.predict(features, verbose=0)
            loss = float(np.mean(np.square(features - reconstruction)))
            data["anomaly_score"] = loss
            data["is_anomaly"] = False
            data["detected_at"] = datetime.utcnow().isoformat()
            return json.dumps(data)

        # Encode numeric + one-hot
        numeric_features = scaler.transform([[value, delay]])
        categorical_features = encoder.transform([[metric_name]])
        features = np.concatenate([numeric_features, categorical_features], axis=1)

        # Predict reconstruction and compute MSE loss
        reconstruction = model.predict(features, verbose=0)
        loss = float(np.mean(np.square(features - reconstruction)))

        # Decision logic with per-metric threshold, hysteresis, N-consecutive, cooldown
        enter_th, exit_th = resolve_threshold(metric_name)
        key = (metric_name, instance)
        st = _get_state(key)

        emitted = False
        if st["in_alarm"]:
            # if already in alarm, leave alarm when below exit threshold
            if loss <= exit_th:
                st["in_alarm"] = False
                st["streak"] = 0
        else:
            # build streak of points above the enter threshold
            if loss >= enter_th:
                st["streak"] += 1
                if st["streak"] >= N_CONSECUTIVE:
                    # check cooldown
                    if now - st["last_emit"] >= COOLDOWN_SEC:
                        st["in_alarm"] = True
                        st["last_emit"] = now
                        emitted = True
                    # if in cooldown, we keep building but don't emit
            else:
                st["streak"] = 0

        # Annotate result (SAME OUTPUT FIELDS)
        data["anomaly_score"] = loss
        data["is_anomaly"] = bool(emitted)  # only True when we actually trigger
        data["detected_at"] = datetime.utcnow().isoformat()

        return json.dumps(data)

    except Exception as e:
        return json.dumps({
            "error": str(e),
            "raw": json_str,
            "detected_at": datetime.utcnow().isoformat()
        })

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

# --- Build pipeline (unchanged shape) ---
ds = env.from_source(
    source,
    watermark_strategy=WatermarkStrategy.for_monotonous_timestamps(),
    source_name="KafkaSource"
)

ds = ds.map(detect_anomaly, output_type=Types.STRING())
ds.sink_to(sink)

# --- Execute Flink Job ---
env.execute("Real-Time Anomaly Detection with Row-Based AutoEncoder (+hysteresis/N/cooldown)")
