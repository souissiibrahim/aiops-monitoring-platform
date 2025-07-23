import os
import json
import faiss
import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

from app.langchain.graphs.rca_graph import run_rca_graph


load_dotenv()

FAISS_INDEX_PATH = "faiss_index/index.faiss"
KNOWN_LOGS_PATH = "faiss_index/known_logs.jsonl"

# Load embedding model
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


# === ✅ Get embedding
def get_embedding(text: str):
    vector = embedding_model.encode([text])[0]
    return np.array(vector, dtype="float32")


# === ✅ Load or create FAISS index
def load_faiss_index(dimension=384):
    if os.path.exists(FAISS_INDEX_PATH):
        return faiss.read_index(FAISS_INDEX_PATH)
    return faiss.IndexFlatL2(dimension)


# === ✅ Match query with FAISS
def match_with_faiss(query_embedding, k=1):
    index = load_faiss_index()
    if index.ntotal == 0:
        return None, None

    query = np.array([query_embedding], dtype="float32")
    distances, indices = index.search(query, k)

    if distances[0][0] > 0.4:  # Threshold to accept the match
        return None, None

    with open(KNOWN_LOGS_PATH, "r") as f:
        known_logs = [json.loads(line) for line in f]

    match = known_logs[indices[0][0]]
    return match["root_cause"], match["recommendation"]


# === ✅ Main function: Suggest Root Cause
def suggest_root_cause(logs: list):
    # Clean logs to ensure they are strings
    logs_clean = [log if isinstance(log, str) else str(log) for log in logs]
    full_log_text = "\n".join(logs_clean)

    embedding = get_embedding(full_log_text)

    # ✅ First: check in FAISS (historical match)
    root_cause, recommendation = match_with_faiss(embedding)
    if root_cause and recommendation:
        return {
            "root_cause": root_cause,
            "confidence": 0.99,
            "recommendation": recommendation
        }

    # ✅ Second: if no match, use LangGraph (Groq LLM)
    result = run_rca_graph(logs_clean)

    # ✅ Third: save to FAISS memory (logs + result)
    os.makedirs(os.path.dirname(KNOWN_LOGS_PATH), exist_ok=True)
    with open(KNOWN_LOGS_PATH, "a") as f:
        f.write(json.dumps({
            "embedding": embedding.tolist(),
            "logs": full_log_text,
            "root_cause": result["root_cause"],
            "recommendation": result["recommendation"]
        }) + "\n")

    return result
