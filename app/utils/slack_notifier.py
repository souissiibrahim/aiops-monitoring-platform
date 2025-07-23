import os
import requests
from dotenv import load_dotenv

load_dotenv()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

def send_to_slack(message, is_block=False):
    payload = {"text": "New message from RCA Agent"}

    if is_block:
        payload["blocks"] = message
    else:
        payload["text"] = message

    response = requests.post(SLACK_WEBHOOK_URL, json=payload)

    if response.status_code != 200:
        raise Exception(f"Slack notification failed: {response.status_code} - {response.text}")
