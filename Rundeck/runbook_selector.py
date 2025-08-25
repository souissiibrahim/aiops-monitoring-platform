import os
import json
from typing import Optional, Dict, Any, List

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from app.db.models.incident_type import IncidentType 

# NEW: DB access for deterministic filtering
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models.runbook import Runbook  # adjust path if different

INDEX_PATH = "Rundeck/faiss_runbook.index"
CATALOG_PATH = "Rundeck/runbook_catalog.jsonl"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Thresholds
REC_CONFIDENCE_MIN = 0.90
FAISS_SIM_MIN = 0.40
ENSEMBLE_MIN = 0.75
TOP_K = 3

_model = None
_index = None
_runbooks = None

def _load_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model

def _load_index():
    global _index
    if _index is None:
        if not os.path.exists(INDEX_PATH):
            raise FileNotFoundError(f"FAISS index not found at {INDEX_PATH}")
        _index = faiss.read_index(INDEX_PATH)  # IP (cosine) index
    return _index

def _load_runbooks():
    global _runbooks
    if _runbooks is None:
        with open(CATALOG_PATH, "r") as f:
            _runbooks = [json.loads(line) for line in f]
    return _runbooks

def _embed(texts: List[str]) -> np.ndarray:
    """Return L2-normalized embeddings for cosine/IP scoring."""
    model = _load_model()
    vecs = model.encode(texts).astype("float32")
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / np.maximum(norms, 1e-12)

def _fetch_candidates_db(incident_type_id: Optional[str], service_id: Optional[str]):
    if not incident_type_id:
        return [], None
    with SessionLocal() as db:
        itype = db.query(IncidentType).filter(IncidentType.incident_type_id == incident_type_id).first()
        q = db.query(Runbook).filter(Runbook.incident_type_id == incident_type_id)
        if service_id:
            q = q.filter(Runbook.service_id == service_id)
        return q.all(), (itype.name if itype else None)

def _rank_candidates_db(cands: List[Runbook], ctx_text: str):
    """Rank DB candidates by semantic similarity + priority (no FAISS needed)."""
    if not cands:
        return None
    texts = [f"{rb.name}. {rb.description or ''}" for rb in cands]
    cand_vecs = _embed(texts)                 # (N, D)
    query_vec = _embed([ctx_text])[0:1, :]    # (1, D)
    sims = (query_vec @ cand_vecs.T).ravel()   # cosine/IP in [−1,1]
    sims = np.clip(sims, 0.0, 1.0)            # clamp to [0,1]

    scored = []
    for rb, sim in zip(cands, sims):
        priority_score = ((rb.priority or 5) / 10.0)
        final = 0.6 * float(sim) + 0.4 * float(priority_score)
        scored.append((final, float(sim), rb))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[0]  # (final, sim, top_rb)

def _fallback_faiss(ctx_text: str):
    """Your existing FAISS-over-catalog path."""
    vec = _embed([ctx_text])
    index = _load_index()
    dists, idxs = index.search(vec, TOP_K)  # IP scores
    runbooks = _load_runbooks()

    candidates = []
    for r in range(min(TOP_K, len(runbooks))):
        i = int(idxs[0][r])
        ip = float(dists[0][r])
        sim = max(0.0, min(1.0, ip))
        candidates.append((sim, i))
    candidates.sort(reverse=True, key=lambda x: x[0])
    if not candidates:
        return None

    best_sim, best_idx = candidates[0]
    matched = runbooks[best_idx]
    return best_sim, matched

def match_recommendation_to_runbook(
    recommendation_text: str,
    recommendation_confidence: float,
    root_cause_text: Optional[str] = None,
    # CHANGED: accept IDs (preferred) + keep names optional if you still send them
    incident_type_id: Optional[str] = None,
    service_id: Optional[str] = None,
    incident_type: Optional[str] = None,
    service_name: Optional[str] = None
) -> Dict[str, Any]:

    if recommendation_confidence < REC_CONFIDENCE_MIN:
        return {
            "auto": False,
            "why": f"Top rec conf {recommendation_confidence:.2f} < {REC_CONFIDENCE_MIN}",
            "job": None,
            "scores": {"rec_conf": recommendation_confidence, "faiss_sim": 0.0, "ensemble": 0.0}
        }

    # Build semantic context
    parts = [recommendation_text]
    if root_cause_text: parts.append(f"root cause: {root_cause_text}")
    # We keep these out of the text to avoid overfitting; IDs are used for hard filtering
    ctx_text = " | ".join(parts)

    # 1) Primary path: DB-filtered candidates by incident_type_id (+ optional service_id)
    cands, incident_type_name = _fetch_candidates_db(incident_type_id, service_id)
    if cands:
        final, sim, top = _rank_candidates_db(cands, ctx_text)
        ensemble = 0.7 * recommendation_confidence + 0.3 * sim
        if sim < FAISS_SIM_MIN:
            return {
                "auto": False,
                "why": f"Similarity {sim:.2f} < {FAISS_SIM_MIN} among incident_type candidates",
                "job": None,
                "scores": {"rec_conf": recommendation_confidence, "faiss_sim": sim, "ensemble": ensemble}
            }
        if ensemble < ENSEMBLE_MIN:
            return {
                "auto": False,
                "why": f"Ensemble {ensemble:.2f} < {ENSEMBLE_MIN}",
                "job": {"job_id": str(top.runbook_id), "name": top.name, "description": top.description},
                "scores": {"rec_conf": recommendation_confidence, "faiss_sim": sim, "ensemble": ensemble}
            }
        return {
            "auto": True,
            "why": "Filtered by incident_type/service; ranked by similarity+priority",
            "incident_type_name": incident_type_name,
            "job": {"job_id": str(top.runbook_id), "name": top.name, "description": top.description},
            "scores": {"rec_conf": recommendation_confidence, "faiss_sim": sim, "ensemble": ensemble}
        }

    # 2) Fallback: no DB candidates → global FAISS over catalog (as you have today)
    faiss_hit = _fallback_faiss(ctx_text)
    if not faiss_hit:
        return {"auto": False, "why": "No candidates available", "job": None, "scores": {}}

    best_sim, matched = faiss_hit
    ensemble = 0.7 * recommendation_confidence + 0.3 * best_sim
    if best_sim < FAISS_SIM_MIN:
        return {
            "auto": False,
            "why": f"FAISS sim {best_sim:.2f} < {FAISS_SIM_MIN}",
            "job": None,
            "scores": {"rec_conf": recommendation_confidence, "faiss_sim": best_sim, "ensemble": ensemble}
        }
    if ensemble < ENSEMBLE_MIN:
        return {
            "auto": False,
            "why": f"Ensemble {ensemble:.2f} < {ENSEMBLE_MIN}",
            "job": {"job_id": matched["job_id"], "name": matched["name"], "description": matched["description"]},
            "scores": {"rec_conf": recommendation_confidence, "faiss_sim": best_sim, "ensemble": ensemble}
        }
    return {
        "auto": True,
        "why": "FAISS fallback passed thresholds",
        "job": {"job_id": matched["job_id"], "name": matched["name"], "description": matched["description"]},
        "scores": {"rec_conf": recommendation_confidence, "faiss_sim": best_sim, "ensemble": ensemble}
    }
