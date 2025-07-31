import os
import json
from typing import TypedDict
from langchain_groq import ChatGroq
from langchain.chains import LLMChain
from langgraph.graph import StateGraph, END
from app.langchain.prompts.root_cause_prompt import root_cause_prompt


# ✅ Define Extended State Schema
class RCAState(TypedDict):
    logs: list[str]
    root_cause: str
    recommendation: str
    confidence: float
    service_name: str
    incident_type: str
    metric_type: str


# ✅ Node 1: Analyze Logs
def analyze_logs(state: RCAState):
    print("🔍 Running Analyze Logs node...")

    llm = ChatGroq(
        groq_api_key=os.getenv("GROQ_API_KEY"),
        model="llama3-8b-8192",
        temperature=0
    )

    chain = LLMChain(llm=llm, prompt=root_cause_prompt)

    # Clean logs and gather context
    logs_clean = [str(log) for log in state.get("logs", [])]
    logs_combined = "\n".join(logs_clean)

    # Prepare input for LLM
    inputs = {
        "logs": logs_combined,
        "incident_type": state.get("incident_type", "Unknown"),
        "metric_type": state.get("metric_type", "Unknown"),
        "service_name": state.get("service_name", "Unknown")
    }

    try:
        response = chain.invoke(inputs)
        raw = response["text"]
        print("📝 Raw LLM response:\n", raw)

        # ✅ Clean markdown formatting like ```json ... ```
        if "```" in raw:
            raw = raw.split("```")[-1].strip()
        raw = raw.strip()

        result = json.loads(raw)

    except Exception as e:
        print(f"❌ Error parsing LLM response: {e}")
        result = {
            "root_cause": "Failed to parse",
            "recommendation": "Check manually",
            "confidence": 0.0
        }

    state.update({
        "root_cause": result.get("root_cause", "N/A"),
        "recommendation": result.get("recommendation", "N/A"),
        "confidence": float(result.get("confidence", 0.0))
    })

    print(f"🧠 RCA Result: {state}")

    if state["confidence"] >= 0.8:
        return state
    else:
        return state, "low_confidence"


# ✅ Node 2: Human Review
def human_review(state: RCAState):
    print("👨‍💻 Human review required (confidence too low).")
    return state


# ✅ Graph Definition
def run_rca_graph(logs, incident_type="Unknown", metric_type="Unknown", service_name="Unknown"):
    graph = StateGraph(RCAState)

    graph.add_node("analyze_logs", analyze_logs)
    graph.add_node("human_review", human_review)

    graph.add_edge("analyze_logs", END)
    graph.add_edge("analyze_logs", "human_review")
    graph.add_edge("human_review", END)

    graph.set_entry_point("analyze_logs")

    app = graph.compile()

    # Full state with context
    state: RCAState = {
        "logs": logs,
        "incident_type": incident_type,
        "metric_type": metric_type,
        "service_name": service_name,
        "root_cause": "",
        "recommendation": "",
        "confidence": 0.0
    }

    result = app.invoke(state)

    return {
        "root_cause": result.get("root_cause", "N/A"),
        "recommendation": result.get("recommendation", "N/A"),
        "confidence": result.get("confidence", 0.0),
        "model": "LangGraph"
    }
