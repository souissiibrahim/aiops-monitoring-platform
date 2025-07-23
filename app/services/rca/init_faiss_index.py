import os
import json
import faiss
import numpy as np
from app.services.rca.smart_suggest_root_cause import get_embedding, FAISS_INDEX_PATH, KNOWN_LOGS_PATH

samples = [
    {
        "logs": "Node Exporter stopped sending metrics. Prometheus scrape failed with timeout.",
        "root_cause": "Node Exporter crash",
        "recommendation": "Restart node_exporter service and check systemd logs."
    },
    {
        "logs": "Elasticsearch cluster status red. Unassigned shards. Write operations failing.",
        "root_cause": "Disk full on Elasticsearch node",
        "recommendation": "Free up disk space or increase volume size."
    },
    {
        "logs": "Grafana dashboard not loading. 502 Bad Gateway from Nginx reverse proxy.",
        "root_cause": "Grafana service down",
        "recommendation": "Restart Grafana container and check logs for crash loops."
    }
]

os.makedirs(os.path.dirname(KNOWN_LOGS_PATH), exist_ok=True)
with open(KNOWN_LOGS_PATH, "w") as f:
    for entry in samples:
        embedding = get_embedding(entry["logs"])
        entry["embedding"] = embedding.tolist()
        f.write(json.dumps(entry) + "\n")

dimension = 384  
index = faiss.IndexFlatL2(dimension)

embeddings = [np.array(entry["embedding"], dtype="float32") for entry in samples]
embedding_matrix = np.vstack(embeddings)

print("Sample embedding shape:", embeddings[0].shape)
print("Stacked embeddings shape:", embedding_matrix.shape)

index.add(embedding_matrix)
faiss.write_index(index, FAISS_INDEX_PATH)
print("✅ FAISS index initialized with sample logs.")
