import pandas as pd
import numpy as np
import os
import json
import joblib
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense
from tensorflow.keras.callbacks import EarlyStopping

# --- Paths ---
CSV_PATH = "/home/ibrahim/fastapi-boilerplate/flink/cleanCSV/cleaned_historical_metrics.csv"
MODEL_DIR = 'model'
os.makedirs(MODEL_DIR, exist_ok=True)

# --- Load Data ---
df = pd.read_csv(CSV_PATH)

# --- Filter and feature build ---
df = df[['metric_name', 'value', 'collection_delay']]  # if delay exists

# --- One-hot encode metric name ---
encoder = OneHotEncoder(sparse_output=False)
encoded_names = encoder.fit_transform(df[['metric_name']])
metric_features = encoder.get_feature_names_out(['metric_name'])

# --- Combine with numeric features ---
X_numeric = df[['value', 'collection_delay']].fillna(0)
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X_numeric)

# --- Final feature matrix ---
X_final = np.concatenate([X_scaled, encoded_names], axis=1)
feature_names = list(X_numeric.columns) + list(metric_features)

# --- Build AutoEncoder ---
input_dim = X_final.shape[1]
input_layer = Input(shape=(input_dim,))
encoded = Dense(32, activation='relu')(input_layer)
encoded = Dense(16, activation='relu')(encoded)
decoded = Dense(32, activation='relu')(encoded)
decoded = Dense(input_dim, activation='linear')(decoded)

autoencoder = Model(inputs=input_layer, outputs=decoded)
autoencoder.compile(optimizer='adam', loss='mse')

# --- Train ---
es = EarlyStopping(monitor='loss', patience=3, restore_best_weights=True)
autoencoder.fit(X_final, X_final, epochs=50, batch_size=64, shuffle=True, callbacks=[es])

# --- Compute threshold ---
reconstructed = autoencoder.predict(X_final, verbose=0)
mse = np.mean(np.power(X_final - reconstructed, 2), axis=1)
threshold = np.percentile(mse, 95)

# --- Save ---
autoencoder.save(os.path.join(MODEL_DIR, 'autoencoder_model'))
joblib.dump(scaler, os.path.join(MODEL_DIR, 'scaler.joblib'))
joblib.dump(encoder, os.path.join(MODEL_DIR, 'encoder.joblib'))

with open(os.path.join(MODEL_DIR, 'feature_names.json'), 'w') as f:
    json.dump(feature_names, f)
with open(os.path.join(MODEL_DIR, 'threshold.json'), 'w') as f:
    json.dump({"threshold": threshold}, f)

print(f"✅ Trained with row-based data. Threshold: {threshold}")
