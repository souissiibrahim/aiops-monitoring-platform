import faiss
import json
from sentence_transformers import SentenceTransformer
import numpy as np
import os

# === Config ===
CATALOG_PATH = "Rundeck/runbook_catalog.jsonl"
INDEX_PATH = "Rundeck/faiss_runbook.index"
ID_MAP_PATH = "Rundeck/runbook_id_map.json"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# === Load model ===
print("🔍 Loading sentence transformer model...")
model = SentenceTransformer(EMBEDDING_MODEL)

# === Load and encode runbook descriptions ===
print("📄 Reading runbook catalog...")
runbooks = []
id_map = {}
descriptions = []

with open(CATALOG_PATH, "r") as f:
    for i, line in enumerate(f):
        item = json.loads(line)
        runbooks.append(item)
        id_map[i] = item["job_id"]
        descriptions.append(f"{item['name']}. {item['description']}")

print(f"📚 Loaded {len(runbooks)} runbooks.")

# === Compute embeddings ===
print("🧠 Encoding descriptions...")
embeddings = model.encode(descriptions, show_progress_bar=True)
embeddings = np.array(embeddings).astype("float32")

# === Create FAISS index ===
print("📦 Building FAISS index...")
index = faiss.IndexFlatIP(embeddings.shape[1])
index.add(embeddings)

# === Save index and ID map ===
print("💾 Saving FAISS index and ID map...")
faiss.write_index(index, INDEX_PATH)
with open(ID_MAP_PATH, "w") as f:
    json.dump(id_map, f)

print(f"✅ FAISS index saved to {INDEX_PATH}")
print(f"✅ ID map saved to {ID_MAP_PATH}")
