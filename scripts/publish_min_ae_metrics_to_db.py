import os, sys, json, joblib, numpy as np, pandas as pd
try:
    from keras.models import load_model
except Exception:
    from tensorflow.keras.models import load_model  # fallback

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db.session import SessionLocal
from app.db.models.model import Model as DBModel

MODEL_NAME  = os.getenv("AE_MODEL_NAME", "ae-metric-anomaly")
MODEL_DIR   = os.getenv("AE_MODEL_DIR", "flink/jobs/model")
CSV_PATH    = os.getenv("AE_TRAIN_CSV", "flink/cleanCSV/cleaned_historical_metrics.csv")

AE_SAVED_DIR = os.path.join(MODEL_DIR, "autoencoder_model")
SCALER_PKL   = os.path.join(MODEL_DIR, "scaler.joblib")
ENCODER_PKL  = os.path.join(MODEL_DIR, "encoder.joblib")
FEAT_JSON    = os.path.join(MODEL_DIR, "feature_names.json")
THRESH_JSON  = os.path.join(MODEL_DIR, "threshold.json")

def _prep_df(df: pd.DataFrame) -> pd.DataFrame:
    if "collection_delay" not in df.columns:
        df["collection_delay"] = 0.0
    df = df[["metric_name", "value", "collection_delay"]].copy()
    df["metric_name"] = df["metric_name"].astype(str)
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0.0)
    df["collection_delay"] = pd.to_numeric(df["collection_delay"], errors="coerce").fillna(0.0)
    return df

def main():
    model   = load_model(AE_SAVED_DIR)
    scaler  = joblib.load(SCALER_PKL)
    encoder = joblib.load(ENCODER_PKL)
    with open(FEAT_JSON, "r") as f:
        feature_names = json.load(f)
    with open(THRESH_JSON, "r") as f:
        thr_payload = json.load(f)

    thr_global = float(thr_payload.get("global", thr_payload.get("threshold", 0.0)))
    hysteresis = thr_payload.get("hysteresis", {"high_pct": 99, "low_pct": 95})

    df = pd.read_csv(CSV_PATH, usecols=["metric_name", "value", "collection_delay"])
    df = _prep_df(df)
    names_encoded = encoder.transform(df[["metric_name"]])
    X_scaled = scaler.transform(df[["value", "collection_delay"]].values)
    X = np.concatenate([X_scaled, names_encoded], axis=1)
    if X.shape[1] != len(feature_names):
        raise ValueError(f"Feature mismatch: X has {X.shape[1]} columns, expected {len(feature_names)}")

    recon = model.predict(X, verbose=0)
    mse = np.mean((X - recon) ** 2, axis=1)
    mse_mean = float(mse.mean())
    mse_std  = float(mse.std())

    metrics_json = {
        "reconstruction": {
            "mse_mean": mse_mean,
            "mse_std":  mse_std,
            "threshold": thr_global
        },
        "thresholds": {
            "global": thr_global,
            "hysteresis": hysteresis
        }
    }

    db = SessionLocal()
    try:
        m = db.query(DBModel).filter(DBModel.name == MODEL_NAME, DBModel.is_deleted == False).first()
        if not m:
            print(f"[WARN] Model row not found for name='{MODEL_NAME}'. Insert it first.")
            return
        # Keep accuracy as-is (no labels) – only update metrics JSON
        m.metrics = metrics_json
        db.add(m)
        db.commit()
        print(f"✅ Updated DB: model='{MODEL_NAME}' metrics={json.dumps(metrics_json)}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
