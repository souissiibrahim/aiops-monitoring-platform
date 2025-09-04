import os, json
from pathlib import Path
import numpy as np, faiss
from sentence_transformers import SentenceTransformer

RAG_DIR   = Path(os.getenv("RAG_DIR", "rag"))
EMB_MODEL = os.getenv("RAG_EMB_MODEL", "all-MiniLM-L6-v2")
IDX_PATH  = RAG_DIR / "faiss.index"
CH_PATH   = RAG_DIR / "chunks.jsonl"

_model = SentenceTransformer(EMB_MODEL)
_index = faiss.read_index(str(IDX_PATH))
_chunks = [json.loads(l) for l in CH_PATH.open("r", encoding="utf-8")]

def search_passages(query: str, k: int = 6):
    vec = _model.encode([query], convert_to_numpy=True, normalize_embeddings=True).astype(np.float32)
    D, I = _index.search(vec, k)
    out=[]
    for idx, score in zip(I[0], D[0]):
        if int(idx) < 0: continue
        ch = _chunks[int(idx)]
        out.append({"text": ch["text"], "source": ch["source"], "score": float(score)})
    return out

def search_with_relevance(query: str, k: int = 6, fetch_k: int = 24, diversify: bool = True):
    results = search_passages(query, k=k, fetch_k=fetch_k, diversify=diversify)
    top_score = max((r["score"] for r in results), default=0.0)
    return results, float(top_score)
