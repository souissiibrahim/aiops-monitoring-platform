# app/chat/agent.py
import os
import re
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple, Optional
import dateutil.parser

from .prompts import POLICY
from . import tools, rag, llm

# ---- Config ----
DEFAULT_WINDOW_MIN = int(os.getenv("ASSISTANT_WINDOW_MIN", "10"))
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.30"))  # tune 0.28–0.35
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "6"))
RAG_FETCH_K = int(os.getenv("RAG_FETCH_K", "24"))
RUNBOOK_HINTS = ("runbook", "runbooks", "playbook", "run book")

API = os.getenv("POWEROPS_API", "http://172.24.68.64:8000").rstrip("/")
VERIFY_SSL = os.getenv("VERIFY_SSL", "true").lower() in ("1", "true", "yes")
TOKEN = os.getenv("POWEROPS_TOKEN")

# ---- Small utils ----
def _isoz(dtobj: datetime) -> str:
    return dtobj.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def _ensure_z(s: str) -> str:
    return s if s.endswith("Z") else s + "Z"

def _shift(iso: str, minutes: int) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return _isoz(dt + timedelta(minutes=minutes))

def _uuid(text: str) -> Optional[str]:
    m = re.search(r"[0-9a-fA-F-]{36}", text)
    return m.group(0) if m else None

def _compute_top_score(passages: List[Dict]) -> float:
    try:
        return float(max((p.get("score", 0.0) for p in passages), default=0.0))
    except Exception:
        return 0.0

def _is_runbook_query(q: str) -> bool:
    ql = q.lower()
    return any(h in ql for h in RUNBOOK_HINTS)

def _owner_str(owner) -> str:
    if isinstance(owner, dict):
        return owner.get("name") or owner.get("team") or owner.get("email") or "—"
    return str(owner) if owner else "—"

# ---- Formatting helpers ----
def _compute_top_score(passages: List[Dict]) -> float:
    if not passages:
        return 0.0
    return max((p.get("score", 0.0) for p in passages), default=0.0)

def _fmt_incident(i: dict) -> str:
    itype = i.get("incident_type", {}).get("name") if isinstance(i.get("incident_type"), dict) else i.get("incident_type")
    sev = i.get("severity_level", {}).get("name") if isinstance(i.get("severity_level"), dict) else i.get("severity_level")
    source_name = i.get("source", {}).get("name") if isinstance(i.get("source"), dict) else i.get("source")
    started = i.get("start_timestamp") or i.get("created_at") or "?"
    return (f"id={i.get('incident_id','?')} • {itype} ({sev}) on {source_name} @ {started}")

def _fmt_passages(passages: List[Dict]) -> str:
    lines = ["## Retrieved Passages (RAG)"]
    for h in passages[:6]:
        src = h.get("source", "?")
        txt = h.get("text", "")[:800]
        lines.append(f"- Source: {src}\n---\n{txt}\n")
    return "\n".join(lines)

def _summarize_logs(loki_json: dict, start: str, end: str) -> str:
    streams = loki_json.get("data", {}).get("result", []) if isinstance(loki_json, dict) else []
    total = sum(len(s.get("values", [])) for s in streams)
    samples = []
    for s in streams[:3]:
        for _, line in s.get("values", [])[:3]:
            samples.append(line.strip()[:180])
    sample_txt = "\n".join(f"• {x}" for x in samples) if samples else "No lines."
    return f"Window {start} → {end}\nTotal lines: {total}\nSamples:\n{sample_txt}"

def _scalar(resp: dict) -> str:
    try:
        return f"{float(resp['data']['result'][0]['value'][1]):.4f}"
    except Exception:
        return "n/a"

# ---- RAG retrieval (supports optional search_with_relevance) ----
def _rag_search(query: str) -> Tuple[List[Dict], float]:
    try:
        from .rag import search_with_relevance  # type: ignore
        passages, top_score = search_with_relevance(query, k=RAG_TOP_K, fetch_k=RAG_FETCH_K, diversify=True)
        return passages, float(top_score)
    except Exception:
        passages = rag.search_passages(query, k=RAG_TOP_K)
        return passages, _compute_top_score(passages)

# ---- HTTP helpers (work even if tools.py lacks helpers) ----
def _http_headers() -> Dict[str, str]:
    h = {"Accept": "application/json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h

def _fetch_runbooks() -> List[dict]:
    # Try tools.get_runbooks first
    try:
        fn = getattr(tools, "get_runbooks", None)
        if callable(fn):
            return fn() or []
    except Exception:
        pass
    # Fallback to HTTP
    r = requests.get(f"{API}/runbooks", headers=_http_headers(), timeout=10, verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json().get("data", []) or []

def _fetch_runbook_by_id(runbook_id: str) -> dict:
    try:
        fn = getattr(tools, "get_runbook_by_id", None)
        if callable(fn):
            rb = fn(runbook_id)
            if rb:
                return rb
    except Exception:
        pass
    r = requests.get(f"{API}/runbooks/{runbook_id}", headers=_http_headers(), timeout=10, verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json().get("data", {}) or {}

def _fetch_runbook_steps(runbook_id: str) -> List[dict]:
    # Try tools.get_runbook_steps first
    try:
        fn = getattr(tools, "get_runbook_steps", None)
        if callable(fn):
            steps = fn(runbook_id)
            if steps is not None:
                return steps
    except Exception:
        pass
    # ✅ Correct path per your router: /runbook-steps/runbook/{id}/steps
    r = requests.get(
        f"{API}/runbook-steps/runbook/{runbook_id}/steps",
        headers=_http_headers(),
        timeout=10,
        verify=VERIFY_SSL,
    )
    r.raise_for_status()
    return r.json().get("data", []) or []

# ---- Runbook answers ----
def _answer_runbook_steps(runbook_id: str) -> Dict:
    # Fetch steps (and a bit of runbook metadata for the header)
    try:
        rb = _fetch_runbook_by_id(runbook_id)
    except Exception:
        rb = {}

    name = rb.get("name") or rb.get("title") or f"Runbook {runbook_id}"
    rtype = (rb.get("incident_type") or {}).get("name") if isinstance(rb.get("incident_type"), dict) else rb.get("incident_type")
    owner = _owner_str(rb.get("owner") or rb.get("team") or rb.get("created_by"))

    try:
        steps = _fetch_runbook_steps(runbook_id)
    except Exception as e:
        return {
            "ok": False,
            "text": (
                f"**{name}** (id={runbook_id})\n"
                f"Type: {rtype or '—'} • Owner: {owner}\n\n"
                f"Steps could not be fetched: {e}\n"
                f"[source: runbook:{runbook_id}]"
            ),
            "sources": [f"runbook:{runbook_id}"],
        }

    if not steps:
        return {
            "ok": True,
            "text": f"**{name}** (id={runbook_id})\nType: {rtype or '—'} • Owner: {owner}\n\nNo steps found.\n\n[source: runbook:{runbook_id}]",
            "sources": [f"runbook:{runbook_id}"],
        }

    # Render ordered step list
    lines = [f"**{name}** (id={runbook_id})", f"Type: {rtype or '—'} • Owner: {owner}", "\n**Steps**:"]
    steps_sorted = sorted(steps, key=lambda s: s.get("order") or s.get("step_order") or s.get("index") or 0)
    for i, st in enumerate(steps_sorted, 1):
        title = st.get("name") or st.get("title") or f"Step {i}"
        sdesc = (st.get("description") or "").strip()
        cmd = (st.get("command") or st.get("cmd") or "").strip()
        lines.append(f"{i}. **{title}**")
        if sdesc:
            lines.append(f"   - {sdesc}")
        if cmd:
            lines.append("```bash\n# command\n" + cmd + "\n```")

    text = "\n".join(lines) + f"\n\n[source: runbook:{runbook_id}]"
    return {"ok": True, "text": text, "sources": [f"runbook:{runbook_id}"]}

def _answer_runbook_by_id(runbook_id: str) -> Dict:
    try:
        rb = _fetch_runbook_by_id(runbook_id)
    except Exception as e:
        return {
            "ok": False,
            "text": (
                "I couldn't fetch that runbook from the API.\n"
                f"- Endpoint tried: {API}/runbooks/{runbook_id}\n"
                f"- Error: {e}"
            ),
            "sources": []
        }

    if not rb:
        return {"ok": False, "text": f"No runbook found with id {runbook_id}.", "sources": []}

    name = rb.get("name") or rb.get("title") or "Unnamed"
    desc = (rb.get("description") or "").strip()
    rtype = (rb.get("incident_type") or {}).get("name") if isinstance(rb.get("incident_type"), dict) else rb.get("incident_type")
    created = rb.get("created_at") or "-"
    updated = rb.get("updated_at") or rb.get("modified_at") or "-"
    owner = _owner_str(rb.get("owner") or rb.get("team") or rb.get("created_by"))

    lines = [
        f"**{name}** (id={runbook_id})",
        f"Type: {rtype or '—'} • Owner: {owner} • Created: {created} • Updated: {updated}",
    ]
    if desc:
        lines.append(desc)

    text = "\n".join(lines) + f"\n\n[source: runbook:{runbook_id}]"
    return {"ok": True, "text": text, "sources": [f"runbook:{runbook_id}"]}

def _answer_runbooks() -> Dict:
    try:
        runbooks = _fetch_runbooks()
    except Exception as e:
        return {
            "ok": False,
            "text": (
                "I couldn't fetch runbooks from the API.\n"
                f"- Endpoint tried: {API}/runbooks\n"
                f"- Error: {e}\n"
                "Verify POWEROPS_API and that /runbooks is reachable."
            ),
            "sources": []
        }

    if not runbooks:
        return {"ok": True, "text": "No runbooks found.", "sources": []}

    lines, srcs = [], []
    for rb in runbooks[:25]:
        rid = rb.get("id") or rb.get("runbook_id") or rb.get("id_runbook")
        name = rb.get("title") or rb.get("name") or "Unnamed"
        desc = (rb.get("description") or "").strip().replace("\n", " ")
        if len(desc) > 120:
            desc = desc[:120] + "…"
        steps = rb.get("steps_count") or rb.get("steps_len") or rb.get("steps") or "-"
        updated = rb.get("updated_at") or rb.get("modified_at") or rb.get("last_run") or "-"
        meta = f"steps:{steps}" if steps != "-" else "steps:-"
        if updated and updated != "-":
            meta += f", updated:{updated}"
        lines.append(f"- {name} (id={rid}) — {meta} [source: runbook:{rid}]" + (f"\n  {desc}" if desc else ""))
        if rid:
            srcs.append(f"runbook:{rid}")

    return {"ok": True, "text": "Here are your runbooks:\n" + "\n".join(lines), "sources": srcs}

# ---- Incident enrichment (embedded RCA/Prediction) ----
def _add_incident_embeds(msgs: List[Dict[str, str]], inc: dict, inc_id: str) -> None:
    rca = tools.extract_rca_from_incident(inc)
    if rca:
        rca_summary = (
            (isinstance(rca, dict) and (
                rca.get("summary") or rca.get("root_cause") or rca.get("analysis") or rca.get("description")
            )) or str(rca)
        )
        msgs.append({"role": "system", "content": f"[rca-embedded] {rca_summary} [source: incident:{inc_id}]"})
    pred = tools.extract_prediction_from_incident(inc)
    if pred:
        if isinstance(pred, dict):
            yhat = pred.get("yhat") or pred.get("value") or pred.get("prediction")
            src = pred.get("source") or pred.get("metric_name") or "prediction"
            msgs.append({"role": "system", "content": f"[prediction-embedded] {src} = {yhat} [source: incident:{inc_id}]"})
        else:
            msgs.append({"role": "system", "content": f"[prediction-embedded] {pred} [source: incident:{inc_id}]"})

# ---- Main entry point expected by /chat/ask ----
def answer(question: str, user: Optional[str] = None) -> dict:
    q = question.strip()
    lq = q.lower()
    sources: List[str] = []
    context_sections: List[str] = []

    # A) Runbook queries
    if _is_runbook_query(lq):
        runbook_id = _uuid(lq)
        if "step" in lq and runbook_id:
            # steps-only view
            return _answer_runbook_steps(runbook_id)
        if runbook_id:
            return _answer_runbook_by_id(runbook_id)
        return _answer_runbooks()

    # B) "last incident" intent
    if "last incident" in lq or ("incident" in lq and "last" in lq):
        inc = tools.get_latest_incidents(1)[0]
        sources.append(inc["incident_id"])
        context_sections.append(f"## Incident\n{_fmt_incident(inc)}")

        sys_msgs = [{"role": "system", "content": POLICY}]
        _add_incident_embeds(sys_msgs, inc, inc["incident_id"])

        itype = inc.get("incident_type", {})
        itype_name = itype.get("name") if isinstance(itype, dict) else itype
        passages, top_score = _rag_search(f"{itype_name} remediation")
        if top_score >= RAG_MIN_SCORE and passages:
            context_sections.append(_fmt_passages(passages))
            sources += [p.get("source", "?") for p in passages[:3]]

        messages = sys_msgs + [
            {"role": "user", "content": f"{q}\n\n---\nCONTEXT:\n" + "\n\n".join(context_sections) + f"\n\nCITE sources: {sources}"}
        ]
        try:
            text = llm.chat(messages)
            return {"ok": True, "text": text, "sources": sources}
        except Exception as e:
            return {"ok": False, "text": f"LLM error: {e}", "sources": sources}

    # C) "logs before incident" intent
    if "log" in lq and ("before" in lq or "prior" in lq) and "incident" in lq:
        iid = _uuid(lq)
        if not iid:
            return {"ok": False, "text": "Please include the incident id (UUID).", "sources": []}
        inc = tools.get_incident(iid)
        sources.append(iid)

        end_iso = _ensure_z(inc.get("start_timestamp") or inc.get("created_at") or _isoz(datetime.utcnow()))
        start_iso = _shift(end_iso, -DEFAULT_WINDOW_MIN)

        src = (inc.get("source", {}) or {}).get("name") if isinstance(inc.get("source"), dict) else inc.get("source")
        selector = f'{{source="{src}"}}' if src else '{job=~".+"}'

        try:
            data, logql = tools.loki_range(selector, start_iso, end_iso, limit=300, direction="backward")
            summary = _summarize_logs(data, start_iso, end_iso)
            context_sections += [
                f"## Incident\n{_fmt_incident(inc)}",
                f"## Logs (bounded to {DEFAULT_WINDOW_MIN}m)\nQuery: {logql}\nSummary:\n{summary}"
            ]
            sources.append(f"logQL:{logql}")
            messages = [
                {"role": "system", "content": POLICY},
                {"role": "user", "content": f"{q}\n\n---\nCONTEXT:\n" + "\n\n".join(context_sections) + f"\n\nCITE sources: {sources}"}
            ]
            text = llm.chat(messages)
            return {"ok": True, "text": text, "sources": sources}
        except Exception as e:
            return {
                "ok": False,
                "text": (
                    "I couldn’t reach Loki or the query failed while fetching logs before the incident.\n"
                    f"- Selector: {selector}\n- Start: {start_iso}\n- End: {end_iso}\n- Error: {e}\n"
                    "Verify LOKI_URL and labels (e.g., {source=\"...\"})."
                ),
                "sources": sources
            }

    # C.2) Logs between timestamps
    if any(w in lq for w in (" log", " logs")) and "between" in lq and (" and " in lq or " to " in lq):
        try:
            times = re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", q)
            if len(times) < 2:
                return {"ok": False, "text": "Please provide two ISO timestamps, e.g. 2025-08-26T13:00:00Z and 2025-08-26T13:07:00Z.", "sources": []}
            start_iso, end_iso = times[0], times[1]

            s_dt = datetime.fromisoformat(start_iso.replace("Z","+00:00"))
            e_dt = datetime.fromisoformat(end_iso.replace("Z","+00:00"))
            if e_dt <= s_dt:
                return {"ok": False, "text": "End time must be after start time.", "sources": []}
            if (e_dt - s_dt).total_seconds() > 24*3600:
                s_dt = e_dt - timedelta(hours=24)
                start_iso = s_dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00","Z")

            m_src = re.search(r"(service|source)\s*[:=]\s*([a-zA-Z0-9_.:-]+)", q)
            source_val = m_src.group(2) if m_src else None

            iid = _uuid(q)
            if not source_val and iid:
                try:
                    inc = tools.get_incident(iid)
                    source_val = (inc.get("source", {}) or {}).get("name") if isinstance(inc.get("source"), dict) else inc.get("source")
                except Exception:
                    source_val = None

            selector = f'{{source="{source_val}"}}' if source_val else '{job=~".+"}'

            m_contains = re.search(r'contains\s+"([^"]+)"', q, re.IGNORECASE)
            logql = selector
            if m_contains:
                term = m_contains.group(1).replace('"', '\\"')
                logql = f'{selector} |= "{term}"'

            LOKI_LIMIT = int(os.getenv("LOKI_LIMIT", "200"))

            data, actual_query = tools.loki_range(logql, start_iso, end_iso, limit=LOKI_LIMIT, direction="backward")
            summary = _summarize_logs(data, start_iso, end_iso)

            context_sections = [
                f"## Logs\nTime range: {start_iso} → {end_iso}\nQuery: {actual_query}\n\nSummary:\n{summary}"
            ]
            srcs = [f"logQL:{actual_query}"]

            messages = [
                {"role": "system", "content": POLICY},
                {"role": "user", "content": f"{q}\n\n---\nCONTEXT:\n" + "\n".join(context_sections) + f"\n\nCITE sources: {srcs}"}
            ]
            text = llm.chat(messages)
            return {"ok": True, "text": text, "sources": srcs}
        except Exception as e:
            return {"ok": False, "text": f"Error fetching logs: {e}", "sources": []}

    # D) "how to fix / commands"
    if any(k in lq for k in ["how can i solve", "how to fix", "commands", "fix "]):
        passages, top_score = _rag_search(q)

        if top_score >= 0.35 and passages:
            sources += [p["source"] for p in passages[:5]]
            context_sections.append(_fmt_passages(passages))
        else:
            context_sections.append("No sufficiently relevant runbook passages found. Using LLM suggestions.")

            iid = _uuid(lq)
            sys_msgs = [{"role": "system", "content": POLICY}]
            if iid:
                try:
                    inc = tools.get_incident(iid)
                    sources.append(iid)
                    context_sections.append(f"## Incident\n{_fmt_incident(inc)}")
                    _add_incident_embeds(sys_msgs, inc, iid)
                except Exception as e:
                    sys_msgs.append({"role": "system", "content": f"[note] incident fetch failed: {e}"})

            messages = sys_msgs + [
                {"role": "user", "content":
                    f"{q}\n\n---\nCONTEXT:\n" + "\n\n".join(context_sections) +
                    f"\n\nCITE sources: {sources}\n\nIf runbooks are missing, ALSO propose AI-suggested investigative steps clearly labeled as 'AI-suggested' (information-only)." }
            ]
            try:
                text = llm.chat(messages)
                return {"ok": True, "text": text, "sources": sources}
            except Exception as e:
                return {"ok": False, "text": f"LLM error: {e}", "sources": sources}


    m_metric = re.search(r"\b(node_[a-zA-Z0-9_:]+)\b", q)
    if m_metric:
        metric_name = m_metric.group(1)
        try:
            result, q_used = tools.prom_instant(metric_name)
            value = _scalar(result)
            context_sections.append(f"## Metric\n{metric_name} = {value}")
            sources.append(f"promQL:{q_used}")

            messages = [
                {"role": "system", "content": POLICY},
                {"role": "user", "content": f"{q}\n\n---\nCONTEXT:\n{metric_name} = {value}\n\nCITE sources: {sources}"}
            ]
            text = llm.chat(messages)
            return {"ok": True, "text": text, "sources": sources}
        except Exception as e:
            return {"ok": False, "text": f"Failed to query metric {metric_name}: {e}", "sources": []}

    # E) status / metrics (example)
    if any(k in lq for k in ["status", "performance", "cpu", "memory", "disk", "utilization"]):
        try:
            # Example queries
            promA, qA = tools.prom_instant(
                'sum(rate(http_requests_total{code=~"2.."}[5m])) / sum(rate(http_requests_total[5m]))'
            )
            cpu, qC = tools.prom_instant('avg(node_cpu_utilization)')
        
            context_sections.append(
                f"## Metrics\nAvailability(5m)={_scalar(promA)}\nCPU avg={_scalar(cpu)}"
            )
            sources += [f"promQL:{qA}", f"promQL:{qC}"]
        except Exception as e:
            context_sections.append(f"## Metrics\nFailed to fetch metrics: {e}")

        messages = [
            {"role": "system", "content": POLICY},
            {"role": "user", "content": f"{q}\n\n---\nCONTEXT:\n" +
                        "\n\n".join(context_sections) + f"\n\nCITE sources: {sources}"}
        ]
        try:
            text = llm.chat(messages)
            return {"ok": True, "text": text, "sources": sources}
        except Exception as e:
            return {"ok": False, "text": f"LLM error: {e}", "sources": sources}

    # F) Fallback → RAG (gated)
    passages, top_score = _rag_search(q)
    if top_score >= RAG_MIN_SCORE and passages:
        # ✅ strong RAG match
        sources += [p.get("source", "?") for p in passages]
        messages = [
            {"role": "system", "content": POLICY},
            {"role": "user", "content": f"{q}\n\n---\nCONTEXT:\n" + _fmt_passages(passages) + f"\n\nCITE sources: {sources}"}
        ]
        try:
            text = llm.chat(messages)
            return {"ok": True, "text": text, "sources": sources}
        except Exception as e:
            return {"ok": False, "text": f"LLM error: {e}", "sources": sources}
    else:
        # ❌ weak or no match → ignore RAG and use Groq LLM directly
        messages = [
            {"role": "system", "content": POLICY},
            {"role": "user", "content": q}
        ]
        try:
            text = llm.chat(messages)
            return {"ok": True, "text": text, "sources": []}
        except Exception as e:
            return {"ok": False, "text": f"LLM error: {e}", "sources": []}

    # Nothing relevant found → guide the user
    return {
        "ok": True,
        "text": (
            "I’m information-only. Try:\n"
            "• “show runbook <uuid>” or “steps for runbook <uuid>”\n"
            "• “what runbooks do I have?”\n"
            "• “5 logs before incident <uuid>”\n"
            "• “how to fix high CPU on <service>” (will use RAG + safe diagnostics)."
        ),
        "sources": []
    }
