import os
import logging
from anthropic import Anthropic

log = logging.getLogger(__name__)

_client = None

SYSTEM_PROMPT = """You are an AI IT helpdesk specialist handling a live phone call.
Your job is to diagnose and resolve common IT issues for end users.

VOICE RULES (critical):
- Respond in plain spoken English only. No bullet points, no markdown, no code blocks.
- Keep responses concise — 2 to 4 sentences maximum per turn.
- Never say "I cannot" without offering a next step.
- Spell out abbreviations on first use (e.g., say "V P N" not "VPN" on first mention).

DIAGNOSTIC APPROACH:
1. Clarify the issue with one targeted question at a time.
2. Once you understand the problem, state your diagnosis clearly.
3. Walk the user through the fix step by step, one step per turn.
4. Confirm each step completed before moving to the next.
5. If the issue requires remote access or a ticket, say so explicitly.

SUPPORTED ISSUE CATEGORIES (you handle these autonomously):
- Password resets and account lockouts
- VPN connectivity problems
- Slow computer / high CPU or memory usage
- Wi-Fi connectivity issues
- Outlook / email not working
- Printer not detected or not printing
- Software not opening or crashing
- Windows update issues
- Disk space warnings

ESCALATION:
- If the issue is hardware failure, data loss, or a security breach, tell the user
  you are logging an urgent ticket and a human technician will call them back.
- Always end escalated calls with: "I've logged a ticket for you. A technician will
  follow up shortly. Have a great day."

TICKET LOGGING SIGNAL:
- When you have enough information to log a ticket, end your response with:
  [LOG_TICKET: <one-line summary of issue and resolution>]
- This tag will be stripped from the spoken response automatically.
- Always include this tag when ending a call, whether resolved or escalated.
"""


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY not set.")
        _client = Anthropic(api_key=api_key)
    return _client


def get_agent_response(history: list[dict]) -> str:
    client = _get_client()

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=history,
    )

    raw_reply = response.content[0].text.strip()
    log.info(f"Raw Claude response: '{raw_reply}'")

    # Extract ticket signal and fire logger if present
    ticket_summary = None
    if "[LOG_TICKET:" in raw_reply:
        start = raw_reply.index("[LOG_TICKET:")
        end = raw_reply.index("]", start) + 1
        ticket_signal = raw_reply[start:end]
        ticket_summary = ticket_signal[len("[LOG_TICKET:"):-1].strip()
        raw_reply = (raw_reply[:start] + raw_reply[end:]).strip()
        log.info(f"Ticket signal: {ticket_summary}")

        # Fire and forget — don't block the voice response
        try:
            from ticket_logger import log_ticket
            log_ticket(summary=ticket_summary, transcript=history)
        except Exception as e:
            log.error(f"Ticket logging failed: {e}")

    return raw_reply


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    print("IT Helpdesk Agent — text mode (type 'quit' to exit)\n")
    history = []
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        history.append({"role": "user", "content": user_input})
        reply = get_agent_response(history)
        print(f"Agent: {reply}\n")
        history.append({"role": "assistant", "content": reply})
