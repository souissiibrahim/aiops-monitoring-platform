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

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


def get_embedding(text: str):
    vector = embedding_model.encode([text])[0]
    return np.array(vector, dtype="float32")


def load_faiss_index(dimension=384):
    if os.path.exists(FAISS_INDEX_PATH):
        return faiss.read_index(FAISS_INDEX_PATH)
    return faiss.IndexFlatL2(dimension)


def match_with_faiss(query_embedding, k=1):
    index = load_faiss_index()
    if index.ntotal == 0:
        return None, None, []

    query = np.array([query_embedding], dtype="float32")
    distances, indices = index.search(query, k)

    distance = distances[0][0]
    if distance > 0.4:
        return None, None, []

    with open(KNOWN_LOGS_PATH, "r") as f:
        known_logs = [json.loads(line) for line in f]

    match = known_logs[indices[0][0]]
    confidence = round(1 - distance, 2)

    # Wrap in new recommendation structure
    return match["root_cause"], [
        {
            "text": match["recommendation"],
            "confidence": confidence
        }
    ], "FAISS"


def suggest_root_cause(logs: list[str], incident_type: str, metric_type: str, service_name: str):
    logs_clean = [log if isinstance(log, str) else str(log) for log in logs]
    full_log_text = "\n".join(logs_clean)

    embedding = get_embedding(full_log_text)

    # 1. Try FAISS
    root_cause, recommendations, model = match_with_faiss(embedding)
    if root_cause and recommendations:
        return {
            "root_cause": root_cause,
            "recommendations": recommendations,
            "model": model
        }

    # 2. Fall back to LangGraph
    result = run_rca_graph(
        logs_clean,
        incident_type=incident_type,
        metric_type=metric_type,
        service_name=service_name
    )

    # Validate result format from LangGraph
    if "recommendations" not in result or not isinstance(result["recommendations"], list):
        result["recommendations"] = [{
            "text": result.get("recommendation", "No recommendation provided."),
            "confidence": result.get("confidence", 0.0)
        }]

    # 3. Save to known logs
    os.makedirs(os.path.dirname(KNOWN_LOGS_PATH), exist_ok=True)
    with open(KNOWN_LOGS_PATH, "a") as f:
        f.write(json.dumps({
            "embedding": embedding.tolist(),
            "logs": full_log_text,
            "root_cause": result["root_cause"],
            "recommendation": result["recommendations"][0]["text"]  # Only saving top one for memory
        }) + "\n")

    return {
        "root_cause": result["root_cause"],
        "recommendations": result["recommendations"],
        "model": result.get("model", "LangGraph")
    }
