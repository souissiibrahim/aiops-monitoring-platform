import pandas as pd
import numpy as np
import os
import json
import joblib
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense
from tensorflow.keras.callbacks import EarlyStopping

# --- Paths ---
CSV_PATH = "/home/ibrahim/fastapi-boilerplate/flink/cleanCSV/cleaned_historical_metrics.csv"
MODEL_DIR = 'model'
os.makedirs(MODEL_DIR, exist_ok=True)

# --- Load Data ---
df = pd.read_csv(CSV_PATH)

# --- Feature Engineering ---
df = df[['metric_name', 'value']]  # only keep metric name + value
pivot_df = df.pivot(columns='metric_name', values='value').fillna(0)

# --- Normalize ---
scaler = StandardScaler()
X_scaled = scaler.fit_transform(pivot_df)

# --- Build AutoEncoder ---
input_dim = X_scaled.shape[1]
input_layer = Input(shape=(input_dim,))
encoded = Dense(64, activation='relu')(input_layer)
encoded = Dense(32, activation='relu')(encoded)
decoded = Dense(64, activation='relu')(encoded)
decoded = Dense(input_dim, activation='linear')(encoded)

autoencoder = Model(inputs=input_layer, outputs=decoded)
autoencoder.compile(optimizer='adam', loss='mse')

# --- Train ---
es = EarlyStopping(monitor='loss', patience=3, restore_best_weights=True)
autoencoder.fit(X_scaled, X_scaled, epochs=50, batch_size=64, shuffle=True, callbacks=[es])

# --- Calculate Reconstruction Error ---
reconstructed = autoencoder.predict(X_scaled, verbose=0)
mse = np.mean(np.power(X_scaled - reconstructed, 2), axis=1)
threshold = np.percentile(mse, 95)  # 95th percentile threshold

feature_names = list(pivot_df.columns)
with open(os.path.join(MODEL_DIR, 'feature_names.json'), 'w') as f:
    json.dump(feature_names, f)

# --- Save ---
autoencoder.save(os.path.join(MODEL_DIR, 'autoencoder_model'))  # SavedModel format (no .h5)
joblib.dump(scaler, os.path.join(MODEL_DIR, 'scaler.joblib'))

with open(os.path.join(MODEL_DIR, 'threshold.json'), 'w') as f:
    json.dump({"threshold": threshold}, f)

print(f"✅ AutoEncoder model saved in SavedModel format. Threshold = {threshold}")
