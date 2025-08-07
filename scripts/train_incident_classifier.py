import pandas as pd
import joblib
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

# === Load and clean data ===
df = pd.read_csv("scripts/incident_type_training_data_large.csv")
df.columns = df.columns.str.strip().str.lower()

# === Encode target ===
le = LabelEncoder()
df["incident_type_encoded"] = le.fit_transform(df["incident_type_name"])

# === One-hot encode metric_name ===
X = pd.get_dummies(df[["metric_name", "value", "confidence", "anomaly_score"]], columns=["metric_name"])

# === Save column order for inference consistency ===
joblib.dump(X.columns.tolist(), "scripts/incident_type_feature_columns.pkl")

# === Train model ===
y = df["incident_type_encoded"]
model = XGBClassifier(use_label_encoder=False, eval_metric="mlogloss")
model.fit(X, y)

# === Save model and encoder ===
joblib.dump(model, "scripts/incident_type_classifier.pkl")
joblib.dump(le, "scripts/incident_type_label_encoder.pkl")

print("✅ Model, encoder, and feature columns saved.")