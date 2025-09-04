import os
import json
import re
from typing import TypedDict, List, Dict, Union
from langchain_groq import ChatGroq
from langchain.chains import LLMChain
from langgraph.graph import StateGraph, END
from app.langchain.prompts.root_cause_prompt import root_cause_prompt


# ✅ RCAState with structured recommendations
class RCAState(TypedDict):
    logs: List[str]
    root_cause: str
    recommendations: List[Dict[str, Union[str, float]]]
    confidence: float
    service_name: str
    incident_type: str
    metric_type: str


# ✅ Node 1: Analyze Logs
def analyze_logs(state: RCAState):
    print("🔍 Running Analyze Logs node...")

    llm = ChatGroq(
        groq_api_key=os.getenv("GROQ_API_KEY"),
        model="llama-3.1-8b-instant",
        temperature=0
    )

    chain = LLMChain(llm=llm, prompt=root_cause_prompt)

    logs_clean = [str(log) for log in state.get("logs", [])]
    logs_combined = "\n".join(logs_clean)

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

        # ✅ Remove markdown formatting and extra explanation
        if "```" in raw:
            raw = raw.split("```")[-1].strip()

        # ✅ Extract JSON block from response using regex
        match = re.search(r'{[\s\S]*}', raw)
        if not match:
            raise ValueError("No valid JSON block found in LLM response")
        json_text = match.group(0)

        parsed = json.loads(json_text)

        # ✅ Normalize format
        root_cause = parsed.get("root_cause", "N/A")
        recommendations = parsed.get("recommendations", [])
        if not isinstance(recommendations, list):
            recommendations = [{
                "text": parsed.get("recommendation", "N/A"),
                "confidence": parsed.get("confidence", 0.0)
            }]

        top_confidence = max((r.get("confidence", 0.0) for r in recommendations), default=0.0)

    except Exception as e:
        print(f"❌ Error parsing LLM response: {e}")
        root_cause = "Failed to parse"
        recommendations = [{
            "text": "Check manually",
            "confidence": 0.0
        }]
        top_confidence = 0.0

    state.update({
        "root_cause": root_cause,
        "recommendations": recommendations,
        "confidence": top_confidence
    })

    print(f"🧠 RCA Result: {state}")
    return state  # ✅ Always return a dict


# ✅ Optional Human Review node (used for fallback paths)
def human_review(state: RCAState):
    print("👨‍💻 Human review required (confidence too low).")
    return state


# ✅ RCA Graph Engine
def run_rca_graph(logs, incident_type="Unknown", metric_type="Unknown", service_name="Unknown"):
    graph = StateGraph(RCAState)

    graph.add_node("analyze_logs", analyze_logs)
    graph.add_node("human_review", human_review)

    graph.add_edge("analyze_logs", END)
    graph.add_edge("analyze_logs", "human_review")
    graph.add_edge("human_review", END)

    graph.set_entry_point("analyze_logs")

    app = graph.compile()

    state: RCAState = {
        "logs": logs,
        "incident_type": incident_type,
        "metric_type": metric_type,
        "service_name": service_name,
        "root_cause": "",
        "recommendations": [],
        "confidence": 0.0
    }

    result = app.invoke(state)

    return {
        "root_cause": result.get("root_cause", "N/A"),
        "recommendations": result.get("recommendations", []),
        "model": "LangGraph"
    }
