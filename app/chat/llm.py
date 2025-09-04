import os, requests

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL    = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")

def chat(messages, temperature=0.2, max_tokens=900):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }
    r = requests.post(url, json=payload, headers=headers, timeout=45)
    if r.status_code != 200:
        # surface the real reason (model invalid, context too big, etc.)
        raise RuntimeError(f"Groq API {r.status_code}: {r.text}\nModel={LLM_MODEL}")
    data = r.json()
    return data["choices"][0]["message"]["content"]
