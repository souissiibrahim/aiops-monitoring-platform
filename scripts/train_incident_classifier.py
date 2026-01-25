#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json
from datetime import datetime, timezone

import pandas as pd
import numpy as np
import joblib
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report
from xgboost import XGBClassifier
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from app.monitor.heartbeat import start_heartbeat
    hb = start_heartbeat("scripts/train_incident_classifier.py", interval_s=30, version="dev")
except Exception:
    hb = None 

from app.db.session import SessionLocal
from app.db.models.model import Model

MODEL_NAME = "xgb-incident-classifier"
DATA_CSV   = os.getenv("INCIDENT_TRAIN_CSV", "scripts/incident_type_training_data_large.csv")
ARTIF_DIR  = os.getenv("INCIDENT_MODEL_DIR", "scripts") 

FEATURE_COLUMNS_PKL = os.path.join(ARTIF_DIR, "incident_type_feature_columns.pkl")
MODEL_PKL           = os.path.join(ARTIF_DIR, "incident_type_classifier.pkl")
LABEL_ENCODER_PKL   = os.path.join(ARTIF_DIR, "incident_type_label_encoder.pkl")


def _set_model_status(db, name: str, status: str, set_trained_at: bool = False, accuracy: float | None = None):
    m = db.query(Model).filter(Model.name == name, Model.is_deleted == False).first()  
    if not m:
        print(f"[WARN] Model row not found for name='{name}'. Did you insert it?")
        return False
    m.last_training_status = status
    if set_trained_at:
        m.last_trained_at = datetime.now(timezone.utc)
    if accuracy is not None:
        m.accuracy = float(accuracy)
    db.add(m)
    db.commit()
    return True


def load_and_prepare():
    df = pd.read_csv(DATA_CSV)
    df.columns = df.columns.str.strip().str.lower()

    required_cols = {"metric_name", "value", "confidence", "anomaly_score", "incident_type_name"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Training CSV missing columns: {missing}")

    df = df.dropna(subset=["incident_type_name"]).copy()

    le = LabelEncoder()
    df["incident_type_encoded"] = le.fit_transform(df["incident_type_name"].astype(str))

    X = pd.get_dummies(
        df[["metric_name", "value", "confidence", "anomaly_score"]],
        columns=["metric_name"],
        dummy_na=False
    ).astype(float)

    y = df["incident_type_encoded"].astype(int)

    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    return X, y, le


def train_and_eval(X, y):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        objective="multi:softprob",
        eval_metric="mlogloss",
        tree_method="hist",
        random_state=42,
        n_jobs=-1
    )

    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    f1w = f1_score(y_test, y_pred, average="weighted")

    print(f"✅ Accuracy: {acc:.4f}  |  F1 (weighted): {f1w:.4f}")
    try:
        print(classification_report(y_test, y_pred, digits=3))
    except Exception:
        pass

    return model, acc, f1w, (X_test.columns.tolist())


def save_artifacts(model, feature_cols, label_encoder):
    os.makedirs(ARTIF_DIR, exist_ok=True)
    joblib.dump(feature_cols, FEATURE_COLUMNS_PKL)
    joblib.dump(model, MODEL_PKL)
    joblib.dump(label_encoder, LABEL_ENCODER_PKL)
    print(f"💾 Saved: {MODEL_PKL}, {LABEL_ENCODER_PKL}, {FEATURE_COLUMNS_PKL}")


def main():
    db = SessionLocal()
    try:
        _set_model_status(db, MODEL_NAME, "running", set_trained_at=False)

        X, y, le = load_and_prepare()

        model, acc, f1w, feat_cols = train_and_eval(X, y)

        save_artifacts(model, feat_cols, le)

        _set_model_status(db, MODEL_NAME, "succeeded", set_trained_at=True, accuracy=float(acc))

        print(json.dumps({
            "model": MODEL_NAME,
            "status": "succeeded",
            "accuracy": round(float(acc), 6),
            "f1_weighted": round(float(f1w), 6),
            "trained_at": datetime.now(timezone.utc).isoformat()
        }, indent=2))

    except Exception as e:
        # mark FAILED (do not set last_trained_at)
        _set_model_status(db, MODEL_NAME, "failed", set_trained_at=False)
        print(f"❌ Training failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
