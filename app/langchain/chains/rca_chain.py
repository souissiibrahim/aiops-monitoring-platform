import json
from langchain.chat_models import ChatOpenAI
from langchain.chains import LLMChain
from app.langchain.prompts.root_cause_prompt import root_cause_prompt


def rca_chain(
    logs: list[str],
    incident_type: str = "Unknown",
    metric_type: str = "Unknown",
    service_name: str = "Unknown"
):
    llm = ChatOpenAI(temperature=0)

    chain = LLMChain(
        llm=llm,
        prompt=root_cause_prompt
    )

    logs_combined = "\n".join(logs)

    try:
        response = chain.invoke({
            "logs": logs_combined,
            "incident_type": incident_type,
            "metric_type": metric_type,
            "service_name": service_name
        })

        result = json.loads(response["text"])  # ChatOpenAI returns dict with key "text"

        return {
            "root_cause": result.get("root_cause", "N/A"),
            "recommendation": result.get("recommendation", "N/A"),
            "confidence": float(result.get("confidence", 0.5)),
            "model": "OpenAI"
        }

    except Exception as e:
        print(f"❌ Error parsing LLM response: {e}")
        return {
            "root_cause": "Parsing error from LLM response",
            "recommendation": "Check logs manually",
            "confidence": 0.0,
            "model": "OpenAI"
        }
