import os
import re
import datetime as dt
from typing import List, Dict, Tuple

from .prompts import POLICY
from .llm import chat
from . import tools

# RAG loader (supports both search_with_relevance and search_passages)
try:
    from .rag import search_with_relevance as _rag_search
    _HAS_SEARCH_WITH_REL = True
except Exception:
    from .rag import search_passages as _rag_search  # type: ignore
    _HAS_SEARCH_WITH_REL = False

# ---------- Heuristics & constants ----------
INCIDENT_ID_RE = re.compile(r"\b[0-9a-fA-F-]{8,}\b")
DOMAIN_HINTS = (
    "incident", "rca", "runbook", "rundeck",
    "promql", "logql", "prometheus", "loki",
    "kafka", "flink", "cpu", "memory", "disk",
    "node_exporter", "service", "endpoint", "telemetry", "severity",
)
RUNBOOK_HINTS = ("runbook", "runbooks", "playbook", "run book")

RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.30"))  # tune 0.28–0.35
RAG_FETCH_K   = int(os.getenv("RAG_FETCH_K", "24"))
RAG_TOP_K     = int(os.getenv("RAG_TOP_K", "6"))

# ---------- Small helpers ----------
def _looks_domain_specific(q: str) -> bool:
    ql = q.lower()
    return any(h in ql for h in DOMAIN_HINTS) or bool(INCIDENT_ID_RE.search(q))

def _is_runbook_query(q: str) -> bool:
    ql = q.lower()
    return any(h in ql for h in RUNBOOK_HINTS)

def _iso(dtobj: dt.datetime) -> str:
    return dtobj.replace(microsecond=0, tzinfo=dt.timezone.utc).isoformat().replace("+00:00", "Z")

def _compute_top_score(passages: List[Dict]) -> float:
    if not passages:
        return 0.0
    try:
        return float(max(p.get("score", 0.0) for p in passages))
    except Exception:
        return 0.0

# ---------- Runbook handling ----------
def _answer_runbooks() -> Dict:
    # Prefer rich cards
    try:
        cards = tools.get_runbook_cards()
    except Exception as e_card:
        try:
            cards = tools.get_runbooks()
        except Exception as e_list:
            return {
                "ok": False,
                "text": (
                    "I couldn't fetch runbooks from the API.\n"
                    f"- Error(card-view): {e_card}\n- Error(list): {e_list}\n"
                    "Verify POWEROPS_API and that /runbooks endpoints are reachable."
                ),
                "sources": []
            }

    if not cards:
        return {"ok": True, "text": "No runbooks found.", "sources": []}

    lines, srcs = [], []
    for rb in cards[:25]:
        rid = rb.get("id") or rb.get("runbook_id") or rb.get("id_runbook")
        name = rb.get("title") or rb.get("name") or "Unnamed"
        desc = (rb.get("description") or "").strip().replace("\n", " ")
        if len(desc) > 120:
            desc = desc[:120] + "…"
        steps = rb.get("steps_count") or rb.get("steps_len") or rb.get("steps") or "-"
        last  = rb.get("last_run") or rb.get("completed_at") or rb.get("updated_at") or "-"
        sr    = rb.get("success_rate")
        meta  = f"steps:{steps}"
        if sr:   meta += f", success:{sr}"
        if last: meta += f", last:{last}"
        lines.append(f"- {name} (id={rid}) — {meta} [source: runbook:{rid}]" + (f"\n  {desc}" if desc else ""))
        if rid: srcs.append(f"runbook:{rid}")

    return {"ok": True, "text": "Here are your runbooks:\n" + "\n".join(lines), "sources": srcs}

# ---------- RAG retrieval with gating ----------
def _retrieve_context(query: str) -> Tuple[List[Dict], float]:
    """
    Returns (passages, top_score). Passages are dicts with {text, source, score}.
    """
    try:
        if _HAS_SEARCH_WITH_REL:
            passages, top_score = _rag_search(query, k=RAG_TOP_K, fetch_k=RAG_FETCH_K, diversify=True)  # type: ignore
            return passages, float(top_score)
        else:
            # Fallback: just search and compute top score
            passages = _rag_search(query, k=RAG_TOP_K)  # type: ignore
            return passages, _compute_top_score(passages)
    except Exception:
        return [], 0.0

def _format_ctx(passages: List[Dict], k: int = 4) -> str:
    seen, ctx = set(), []
    for p in passages:
        if p.get("source") in seen:
            continue
        seen.add(p.get("source"))
        ctx.append(f"---\n{p.get('text','')}\n[source: {p.get('source','?')}] (score={float(p.get('score',0.0)):.3f})")
        if len(ctx) >= k:
            break
    return "\n".join(ctx)

# ---------- Incident + logs/metrics helpers ----------
def _add_incident_context(msgs: List[Dict[str, str]], inc_id: str) -> None:
    inc = tools.get_incident(inc_id)
    msgs.append({
        "role": "system",
        "content": (
            f"[incident] id={inc_id} service={inc.get('service_name','?')} "
            f"severity={inc.get('severity','?')} created_at={inc.get('created_at')} "
            f"[source: incident:{inc_id}]"
        )
    })
    # embedded RCA/Prediction (no direct endpoints)
    rca  = tools.extract_rca_from_incident(inc)
    pred = tools.extract_prediction_from_incident(inc)
    if rca:
        rca_summary = (
            (isinstance(rca, dict) and (
                rca.get("summary") or rca.get("root_cause") or rca.get("analysis") or rca.get("description")
            )) or str(rca)
        )
        msgs.append({"role": "system", "content": f"[rca-embedded] {rca_summary} [source: incident:{inc_id}]"})
    if pred:
        if isinstance(pred, dict):
            yhat = pred.get("yhat") or pred.get("value") or pred.get("prediction")
            src  = pred.get("source") or pred.get("metric_name") or "prediction"
            msgs.append({"role": "system", "content": f"[prediction-embedded] {src} = {yhat} [source: incident:{inc_id}]"})
        else:
            msgs.append({"role": "system", "content": f"[prediction-embedded] {pred} [source: incident:{inc_id}]"})

def _fetch_loki_around(inc_created_iso: str, selector: str, minutes_before=5, minutes_after=0, limit=300):
    try:
        start, end = tools.incident_window({"created_at": inc_created_iso}, minutes_before=minutes_before, minutes_after=minutes_after)
        data, logql = tools.loki_range(selector, start, end, limit=limit, direction="backward")
        return data, logql, None
    except Exception as e:
        return None, None, e

# ---------- Main entry ----------
def answer(user_query: str, user: str = "user") -> Dict:
    msgs: List[Dict[str, str]] = [{"role": "system", "content": POLICY.strip()}]
    sources: List[str] = []

    # 1) Catalog routing: runbooks
    if _is_runbook_query(user_query):
        return _answer_runbooks()

    # 2) RAG (gated) for domain-ish queries
    USE_RAG = False
    passages: List[Dict] = []
    if _looks_domain_specific(user_query):
        passages, top_score = _retrieve_context(user_query)
        USE_RAG = top_score >= RAG_MIN_SCORE and bool(passages)

    if USE_RAG:
        msgs.append({"role": "system", "content": "Retrieved context:\n" + _format_ctx(passages, k=4)})
        sources.extend(list({f"path:{p.get('source')}" for p in passages if p.get("source")}))  # unique

    else:
        msgs.append({"role": "system", "content": "No internal documents relevant above threshold; answer without RAG context."})

    # 3) Incident context if an ID is present
    m = INCIDENT_ID_RE.search(user_query)
    if m:
        inc_id = m.group(0)
        try:
            _add_incident_context(msgs, inc_id)
            sources.append(f"incident:{inc_id}")
        except Exception as e:
            msgs.append({"role": "system", "content": f"[note] incident fetch failed: {e}"})

    # 4) Attach the user message
    msgs.append({"role": "user", "content": user_query})

    # 5) Call LLM
    try:
        text = chat(msgs, temperature=0.2, max_tokens=900)
        return {"ok": True, "text": text, "sources": list(dict.fromkeys(sources))}
    except Exception as e:
        return {
            "ok": False,
            "text": (
                "The assistant could not complete the request due to an LLM error.\n"
                f"- Error: {e}\n"
                "Check GROQ_API_KEY / LLM_MODEL and retry."
            ),
            "sources": list(dict.fromkeys(sources)),
        }
