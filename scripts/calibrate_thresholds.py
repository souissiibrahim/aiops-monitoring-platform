import os, json, numpy as np, pandas as pd, joblib
import tensorflow as tf

# --- paths (respecte ton projet) ---
MODEL_DIR = os.getenv("AE_MODEL_DIR", "flink/jobs/model")
CSV_PATH  = os.getenv("AE_TRAIN_CSV", "flink/cleanCSV/cleaned_historical_metrics.csv")

SCALER_PKL   = os.path.join(MODEL_DIR, "scaler.joblib")
ENCODER_PKL  = os.path.join(MODEL_DIR, "encoder.joblib")
FEAT_JSON    = os.path.join(MODEL_DIR, "feature_names.json")
AE_SAVED_DIR = os.path.join(MODEL_DIR, "autoencoder_model")
THRESH_JSON  = os.path.join(MODEL_DIR, "threshold.json")

EPSILON = float(os.getenv("AE_THRESH_EPS", "1e-6"))
P_GLOBAL = 99  # p99 global
P_PER_METRIC = 99  

# --- load artifacts ---
df = pd.read_csv(CSV_PATH, usecols=["metric_name", "value", "collection_delay"])
df["metric_name"] = df["metric_name"].astype(str)
df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0.0)
df["collection_delay"] = pd.to_numeric(df["collection_delay"], errors="coerce").fillna(0.0)

scaler = joblib.load(SCALER_PKL)
encoder = joblib.load(ENCODER_PKL)
with open(FEAT_JSON, "r") as f:
    feature_names = json.load(f)
model = tf.keras.models.load_model(AE_SAVED_DIR)

# --- build features with saved pipeline (alignement garanti) ---
names_encoded = encoder.transform(df[["metric_name"]])
X_scaled = scaler.transform(df[["value", "collection_delay"]].values)
X = np.concatenate([X_scaled, names_encoded], axis=1)
assert X.shape[1] == len(feature_names), f"Feature mismatch {X.shape[1]} vs {len(feature_names)}"

# --- reconstruction errors ---
recon = model.predict(X, verbose=0)
mse = np.mean((X - recon) ** 2, axis=1)

# --- thresholds ---
global_p = float(np.percentile(mse, P_GLOBAL))
global_th = max(global_p, EPSILON)

by_metric = {}
for name, idx in df.groupby("metric_name").groups.items():
    m = float(np.percentile(mse[list(idx)], P_PER_METRIC))
    by_metric[str(name)] = max(m, EPSILON)

payload = {
    # compat legacy reader:
    "threshold": global_th,
    # enriched schema:
    "global": global_th,
    "by_metric": by_metric,
    "hysteresis": {"high_pct": 99, "low_pct": 95},
    "epsilon": EPSILON,
    "based_on": {"csv": CSV_PATH, "p_global": P_GLOBAL, "p_per_metric": P_PER_METRIC}
}

with open(THRESH_JSON, "w") as f:
    json.dump(payload, f)
print(f"✅ thresholds written to {THRESH_JSON} (global={global_th:.6e}, metrics={len(by_metric)})")
