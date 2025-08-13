from typing import TypedDict, Optional, Dict, Any
from langgraph.graph import StateGraph, END
from datetime import datetime

from Rundeck.runbook_selector import match_recommendation_to_runbook
from app.utils.slack_notifier import send_to_slack
from app.services.remediation_orchestrator import run_auto_remediation


# ---- Graph State ----
class RemediationState(TypedDict, total=False):
    incident_id: str
    service: str
    incident_type_id: Optional[str]
    incident_type_name: Optional[str]        # filled from selector when available
    root_cause: Optional[str]
    recommendation_text: str
    recommendation_confidence: float

    # Filled by nodes:
    decision: Optional[Dict[str, Any]]
    execution: Optional[Dict[str, Any]]
    human_required: bool
    error: Optional[str]


# ---- Nodes ----
def node_match_runbook(state: RemediationState) -> RemediationState:
    decision = match_recommendation_to_runbook(
        recommendation_text=state["recommendation_text"],
        recommendation_confidence=state["recommendation_confidence"],
        root_cause_text=state.get("root_cause"),
        incident_type_id=state.get("incident_type_id"),
        service_id=None,  # intentionally unused for now
    )
    state["decision"] = decision
    if decision.get("incident_type_name"):
        state["incident_type_name"] = decision["incident_type_name"]
    return state


def node_decide(state: RemediationState) -> RemediationState:
    dec = state.get("decision") or {}
    state["human_required"] = not dec.get("auto", False)
    return state


def node_trigger_orchestrator(state: RemediationState) -> RemediationState:
    """
    Auto path: call orchestrator to create/update response_actions, flip incident status,
    trigger Rundeck and poll to completion.
    Human path (no-auto): create Pending response_action with reason.
    """
    dec = state.get("decision") or {}
    job = dec.get("job")
    if not job:
        # No candidate runbook -> require human review (Pending will be created below via human node)
        state["human_required"] = True
        return state

    try:
        if not dec.get("auto", False):
            # Create Pending action only (no execution), with explanation
            reason = dec.get("why", "Thresholds not met / policy requires approval")
            result = run_auto_remediation(
                incident_id=state["incident_id"],
                job=job,
                argstring="",  # not executed now
                human_reason_if_skip=reason,
            )
            state["execution"] = result
            state["human_required"] = True
            return state

        # Auto execution path
        argstring = f"-incident_id {state['incident_id']} -service {state['service']}"
        result = run_auto_remediation(
            incident_id=state["incident_id"],
            job=job,
            argstring=argstring,
        )
        state["execution"] = result
        state["human_required"] = not result.get("ok", False)

    except Exception as e:
        state["error"] = f"Orchestrator failed: {e}"
        state["human_required"] = True

    return state


def node_request_human(state: RemediationState) -> RemediationState:
    dec = state.get("decision") or {}
    why = dec.get("why", "Unspecified")
    scores = dec.get("scores", {})
    job = dec.get("job")

    msg = (
        f"🧑‍⚖️ *Human review required for remediation*\n"
        f"• Incident: `{state['incident_id']}`  Service: `{state['service']}`\n"
        f"• Incident Type: `{state.get('incident_type_name') or state.get('incident_type_id')}`\n"
        f"• Recommendation: _{state['recommendation_text']}_  (conf={state['recommendation_confidence']:.2f})\n"
        f"• Reason: {why}\n"
        f"• Scores: {scores}\n"
        f"• Candidate job: {job}\n"
    )
    try:
        send_to_slack(msg)
    except Exception:
        pass
    return state


# ---- Graph ----
def build_remediation_graph():
    g = StateGraph(RemediationState)

    g.add_node("match_runbook", node_match_runbook)
    g.add_node("decide", node_decide)
    g.add_node("trigger_orchestrator", node_trigger_orchestrator)
    g.add_node("human", node_request_human)

    g.set_entry_point("match_runbook")

    # Always go match -> decide -> trigger_orchestrator
    g.add_edge("match_runbook", "decide")
    g.add_edge("decide", "trigger_orchestrator")

    # After orchestrator, if human is still required (non-auto or error), send the Slack
    def needs_human(state: RemediationState):
        return state.get("human_required", False)

    g.add_conditional_edges("trigger_orchestrator", needs_human, {
        True: "human",
        False: END,
    })

    # Human path ends the graph
    g.add_edge("human", END)

    return g.compile()


# Convenience function
def run_remediation_graph(payload: Dict[str, Any]) -> Dict[str, Any]:
    app = build_remediation_graph()
    return app.invoke(payload)
