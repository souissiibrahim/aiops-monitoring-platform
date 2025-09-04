import os, sys, json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import joblib

# --- DEBUG GUARD: check TensorFlow/Keras environment early ---
try:
    import tensorflow as tf
    import keras
    from keras import Model as KModel
    from keras.layers import Input, Dense
    from keras.callbacks import EarlyStopping
    print(f"[env-check] Python interpreter: {sys.executable}", file=sys.stderr)
    print(f"[env-check] TensorFlow: {getattr(tf, '__version__', '?')}", file=sys.stderr)
    print(f"[env-check] Keras: {getattr(keras, '__version__', '?')}", file=sys.stderr)
except Exception as e:
    print("[env-check] TensorFlow/Keras import failed:", e, file=sys.stderr)
    print("[env-check] Python interpreter:", sys.executable, file=sys.stderr)
    sys.exit(2)

from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.metrics import roc_auc_score

# --- Make project imports work when run as a script ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --- Heartbeat (optional) ---
try:
    from app.monitor.heartbeat import start_heartbeat
    hb = start_heartbeat("scripts/train_autoencoder.py", interval_s=20, version="1.0")
except Exception:
    hb = None

from app.db.session import SessionLocal
from app.db.models.model import Model as DBModel  # avoid clash with Keras Model
from sqlalchemy.orm import Session


MODEL_NAME = os.getenv("AE_MODEL_NAME", "ae-metric-anomaly")

CSV_PATH   = os.getenv("AE_TRAIN_CSV", "/home/ibrahim/fastapi-boilerplate/flink/cleanCSV/cleaned_historical_metrics.csv")
LABELS_CSV = os.getenv("AE_LABELS_CSV", "")  # optional labeled eval

MODEL_DIR  = os.getenv("AE_MODEL_DIR", "model")
os.makedirs(MODEL_DIR, exist_ok=True)

SCALER_PKL   = os.path.join(MODEL_DIR, "scaler.joblib")
ENCODER_PKL  = os.path.join(MODEL_DIR, "encoder.joblib")
FEAT_JSON    = os.path.join(MODEL_DIR, "feature_names.json")
THRESH_JSON  = os.path.join(MODEL_DIR, "threshold.json")
AE_SAVED_DIR = os.path.join(MODEL_DIR, "autoencoder_model")  # TF SavedModel dir


# -------------------------
# DB helpers
# -------------------------
def _set_model_status(db: Session, name: str, status: str, set_trained_at: bool = False, accuracy: float | None = None):
    m = db.query(DBModel).filter(DBModel.name == name, DBModel.is_deleted == False).first()  # noqa: E712
    if not m:
        print(f"[WARN] Model row not found for name='{name}'. Did you insert it?")
        return False
    m.last_training_status = status
    if set_trained_at:
        m.last_trained_at = datetime.now(timezone.utc)
    if accuracy is not None:
        try:
            m.accuracy = float(accuracy)
        except Exception:
            pass
    db.add(m)
    db.commit()
    return True


# -------------------------
# Data prep utilities
# -------------------------
def _one_hot():
    # handle sklearn version differences
    try:
        return OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    except TypeError:
        return OneHotEncoder(sparse=False, handle_unknown="ignore")

def build_features(df: pd.DataFrame):
    # required columns (adjust if your CSV guarantees a different set)
    if "collection_delay" not in df.columns:
        df["collection_delay"] = 0.0

    df = df[["metric_name", "value", "collection_delay"]].copy()
    df["metric_name"] = df["metric_name"].astype(str)
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0.0)
    df["collection_delay"] = pd.to_numeric(df["collection_delay"], errors="coerce").fillna(0.0)

    enc = _one_hot()
    names_encoded = enc.fit_transform(df[["metric_name"]])
    metric_features = enc.get_feature_names_out(["metric_name"])

    scaler = StandardScaler()
    X_numeric = df[["value", "collection_delay"]].values
    X_scaled = scaler.fit_transform(X_numeric)

    X_final = np.concatenate([X_scaled, names_encoded], axis=1)
    feature_names = ["value", "collection_delay"] + list(metric_features)

    return X_final, feature_names, scaler, enc


def build_features_with_known(df: pd.DataFrame, scaler: StandardScaler, enc: OneHotEncoder, known_features: list[str]):
    if "collection_delay" not in df.columns:
        df["collection_delay"] = 0.0
    df = df[["metric_name", "value", "collection_delay"]].copy()
    df["metric_name"] = df["metric_name"].astype(str)
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0.0)
    df["collection_delay"] = pd.to_numeric(df["collection_delay"], errors="coerce").fillna(0.0)

    names_encoded = enc.transform(df[["metric_name"]])
    X_numeric = df[["value", "collection_delay"]].values
    X_scaled = scaler.transform(X_numeric)
    X = np.concatenate([X_scaled, names_encoded], axis=1)

    # ensure column alignment (should already match if encoders are same)
    assert X.shape[1] == len(known_features), f"Feature mismatch: X has {X.shape[1]}, expected {len(known_features)}"
    return X


# -------------------------
# Model building
# -------------------------
def build_autoencoder(input_dim: int) -> KModel:
    inp = Input(shape=(input_dim,))
    x = Dense(32, activation="relu")(inp)
    x = Dense(16, activation="relu")(x)
    x = Dense(32, activation="relu")(x)
    out = Dense(input_dim, activation="linear")(x)
    ae = KModel(inputs=inp, outputs=out)
    ae.compile(optimizer="adam", loss="mse")
    return ae


def main():
    db = SessionLocal()
    try:
        # mark RUNNING
        _set_model_status(db, MODEL_NAME, "running", set_trained_at=False)

        # --- Load data ---
        df = pd.read_csv(CSV_PATH)
        X_final, feature_names, scaler, encoder = build_features(df)

        # --- Train AE ---
        ae = build_autoencoder(X_final.shape[1])
        es = EarlyStopping(monitor="loss", patience=3, restore_best_weights=True)
        ae.fit(X_final, X_final, epochs=50, batch_size=64, shuffle=True, callbacks=[es], verbose=1)

        # --- Train reconstruction stats & threshold ---
        reconstructed = ae.predict(X_final, verbose=0)
        mse = np.mean((X_final - reconstructed) ** 2, axis=1)
        threshold = float(np.percentile(mse, 95))

        # --- Save artifacts ---
        os.makedirs(MODEL_DIR, exist_ok=True)
        ae.save(AE_SAVED_DIR)  # SavedModel dir
        joblib.dump(scaler, SCALER_PKL)
        joblib.dump(encoder, ENCODER_PKL)
        with open(FEAT_JSON, "w") as f:
            json.dump(feature_names, f)
        with open(THRESH_JSON, "w") as f:
            json.dump({"threshold": threshold}, f)
        print(f"✅ Trained AE. Threshold (95p): {threshold:.6f}")

        # --- Optional: evaluate with labels (if provided) ---
        acc_to_store = None
        if LABELS_CSV and os.path.exists(LABELS_CSV):
            try:
                df_test = pd.read_csv(LABELS_CSV)
                if "is_anomaly" in df_test.columns:
                    y_true = pd.to_numeric(df_test["is_anomaly"], errors="coerce").fillna(0).astype(int).values
                    X_test = build_features_with_known(df_test, scaler, encoder, feature_names)
                    recon = ae.predict(X_test, verbose=0)
                    err = np.mean((X_test - recon) ** 2, axis=1)
                    # ROC-AUC on reconstruction error as anomaly score
                    auc = roc_auc_score(y_true, err)
                    acc_to_store = float(auc)
                    print(f"📈 Labeled evaluation ROC-AUC: {auc:.4f}")
                else:
                    print("⚠️ LABELS_CSV provided but no 'is_anomaly' column found. Skipping accuracy calc.")
            except Exception as e:
                print(f"⚠️ Labeled evaluation failed: {e}")

        # --- Mark SUCCEEDED (+ last_trained_at) and optionally write accuracy ---
        _set_model_status(db, MODEL_NAME, "succeeded", set_trained_at=True, accuracy=acc_to_store)

    except Exception as e:
        _set_model_status(db, MODEL_NAME, "failed", set_trained_at=False)
        print(f"❌ AutoEncoder training failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
