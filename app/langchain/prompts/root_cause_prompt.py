from langchain.prompts import PromptTemplate

root_cause_prompt = PromptTemplate(
    input_variables=["logs"],
    template="""
You are an expert DevOps AI assistant. Your job is to perform Root Cause Analysis (RCA) based on system logs.

## Your tasks:
1. Carefully analyze the logs.
2. Identify the root cause of the incident.
3. Suggest a clear and actionable recommendation to fix or prevent the issue.
4. Provide a confidence level (between 0 and 1) based on how clear the logs are.

## Rules for confidence:
- Confidence >= 0.9 → If the logs clearly point to a root cause with no ambiguity.
- Confidence between 0.6 and 0.89 → If the logs suggest a probable cause but there is some uncertainty.
- Confidence < 0.6 → If the logs are insufficient, noisy, or inconclusive.

## Logs to analyze:
{logs}

## Expected output:
Respond strictly in the following JSON format (no extra text):
{{
  "root_cause": "...",
  "recommendation": "...",
  "confidence": 0.85
}}
"""
)
