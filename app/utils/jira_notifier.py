from jira import JIRA
import os
from dotenv import load_dotenv

load_dotenv()

def get_jira_client():
    options = {"server": os.getenv("JIRA_URL")}
    return JIRA(
        options,
        basic_auth=(os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN"))
    )

def create_jira_ticket(summary, description):
    jira = get_jira_client()
    issue = jira.create_issue(
        project=os.getenv("JIRA_PROJECT_KEY"),
        summary=summary,
        description=description,
        issuetype={"name": "Task"}  # or "Incident"
    )
    print(f"✅ Jira ticket created: {issue.key}")
    return issue.key
