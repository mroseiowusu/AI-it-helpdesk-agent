import os
import logging
import requests

log = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"
TEAM_ID = "5a834841-6f92-435f-bad9-4221bf3385ea"
PRIORITY_MAP = {"urgent": 1, "high": 2, "medium": 3, "low": 4}

def log_ticket(summary: str, transcript: list[dict] = None, priority: str = "medium") -> dict:
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        log.error("LINEAR_API_KEY not set")
        return {"error": "LINEAR_API_KEY not set"}

    transcript_text = ""
    if transcript:
        lines = []
        for msg in transcript:
            role = "Caller" if msg["role"] == "user" else "Agent"
            lines.append(f"**{role}:** {msg['content']}")
        transcript_text = "\n\n".join(lines)

    description = f"## Issue Summary\n{summary}\n\n## Call Transcript\n{transcript_text or '_No transcript_'}\n\n---\n_Auto-logged by IT Helpdesk Agent_"

    mutation = """
    mutation CreateIssue($title: String!, $description: String!, $teamId: String!, $priority: Int!) {
        issueCreate(input: { title: $title, description: $description, teamId: $teamId, priority: $priority }) {
            success
            issue { id identifier url }
        }
    }
    """
    try:
        response = requests.post(
            LINEAR_API_URL,
            json={"query": mutation, "variables": {"title": summary, "description": description, "teamId": TEAM_ID, "priority": PRIORITY_MAP.get(priority, 3)}},
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("data", {}).get("issueCreate", {}).get("success"):
            issue = data["data"]["issueCreate"]["issue"]
            log.info(f"Ticket created: {issue['identifier']} — {issue['url']}")
            return issue
        return {"error": str(data)}
    except Exception as e:
        log.error(f"Failed to create ticket: {e}")
        return {"error": str(e)}
