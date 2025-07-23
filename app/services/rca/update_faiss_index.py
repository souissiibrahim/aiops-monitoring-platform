import os
import json
import faiss
import numpy as np
from app.services.rca.smart_suggest_root_cause import get_embedding, FAISS_INDEX_PATH, KNOWN_LOGS_PATH

def append_to_faiss(logs: list[str], root_cause: str, recommendation: str):
    full_log_text = "\n".join(logs)
    embedding = get_embedding(full_log_text)

    entry = {
        "embedding": embedding.tolist(),
        "logs": full_log_text,
        "root_cause": root_cause,
        "recommendation": recommendation
    }
    os.makedirs(os.path.dirname(KNOWN_LOGS_PATH), exist_ok=True)
    with open(KNOWN_LOGS_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

    if os.path.exists(FAISS_INDEX_PATH):
        index = faiss.read_index(FAISS_INDEX_PATH)
    else:
        index = faiss.IndexFlatL2(len(embedding))

    index.add(np.array([embedding], dtype="float32"))
    faiss.write_index(index, FAISS_INDEX_PATH)
    print("🧠 Auto-learn: New RCA embedded and indexed.")
