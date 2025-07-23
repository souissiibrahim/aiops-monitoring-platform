from langchain.chat_models import ChatOpenAI
from langchain.chains import LLMChain
from app.langchain.prompts.root_cause_prompt import root_cause_prompt
import json


def rca_chain(logs):
    llm = ChatOpenAI(temperature=0)

    chain = LLMChain(
        llm=llm,
        prompt=root_cause_prompt
    )

    logs_combined = "\n".join(logs)

    response = chain.run({"logs": logs_combined})

    try:
        result = json.loads(response)
        return {
            "root_cause": result.get("root_cause", "N/A"),
            "recommendation": result.get("recommendation", "N/A"),
            "confidence": float(result.get("confidence", 0.5))
        }
    except Exception as e:
        print(f"❌ Error parsing LLM response: {e}")
        return {
            "root_cause": "Parsing error from LLM response",
            "recommendation": "Check logs manually",
            "confidence": 0.0
        }
