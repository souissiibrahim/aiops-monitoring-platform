import os
import json
from typing import TypedDict
from langchain_groq import ChatGroq
from langchain.chains import LLMChain
from langgraph.graph import StateGraph, END
from app.langchain.prompts.root_cause_prompt import root_cause_prompt


# ✅ Define State Schema
class RCAState(TypedDict):
    logs: list[str]
    root_cause: str
    recommendation: str
    confidence: float


# ✅ Node 1: Analyze Logs
def analyze_logs(state: RCAState):
    print("🔍 Running Analyze Logs node...")

    llm = ChatGroq(
        groq_api_key=os.getenv("GROQ_API_KEY"),
        model="llama3-8b-8192",
        temperature=0
    )

    chain = LLMChain(llm=llm, prompt=root_cause_prompt)

    logs_list = state.get("logs", [])
    logs_clean = [str(log) for log in logs_list]
    logs_combined = "\n".join(logs_clean)

    response = chain.invoke({"logs": logs_combined})  # ✅ Use invoke instead of run

    try:
        result = json.loads(response["text"])  # ✅ For correct response parsing with LLMChain
    except Exception:
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
        return state  # ✅ JUST RETURN STATE if going to END
    else:
        return state, "low_confidence"


# ✅ Node 2: Human Review
def human_review(state: RCAState):
    print("👨‍💻 Human review required (confidence too low).")
    approved = True
    return state  # ✅ Always ends


# ✅ Graph Definition
def run_rca_graph(logs):
    graph = StateGraph(RCAState)

    graph.add_node("analyze_logs", analyze_logs)
    graph.add_node("human_review", human_review)

    # ✅ Add edges
    graph.add_edge("analyze_logs", END)                # if confidence is high
    graph.add_edge("analyze_logs", "human_review")     # if label is low_confidence
    graph.add_edge("human_review", END)                # after human review

    graph.set_entry_point("analyze_logs")

    app = graph.compile()

    state = {"logs": logs}
    result = app.invoke(state)

    return {
        "root_cause": result.get("root_cause", "N/A"),
        "recommendation": result.get("recommendation", "N/A"),
        "confidence": result.get("confidence", 0.0)
    }
