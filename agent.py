"""
agent.py — AI Reasoning Layer (Claude API via Anthropic SDK)
============================================================
This module takes a conversation history and returns the agent's next reply.

The system prompt is the agent's "brain" — it defines:
  - Its role (IT helpdesk specialist)
  - Its escalation logic
  - How it structures its responses for voice (no markdown, short sentences)
  - What actions it can signal (future: trigger remote tools)

Install:
    pip install anthropic

Set env var:
    ANTHROPIC_API_KEY=your_key_here
"""

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
- If the issue is hardware failure, data loss, or a security breach → tell the user
  you are logging an urgent ticket and a human technician will call them back.
- Always end escalated calls with: "I've logged a ticket for you. A technician will
  follow up shortly. Have a great day."

TICKET LOGGING SIGNAL:
- When you have enough information to log a ticket (even a resolved one), end your
  response with the tag: [LOG_TICKET: <one-line summary of issue and resolution>]
  This tag will be stripped from the spoken response automatically.
"""


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY environment variable not set.")
        _client = Anthropic(api_key=api_key)
    return _client


def get_agent_response(history: list[dict]) -> str:
    """
    Given a conversation history (list of {"role": "user"/"assistant", "content": str}),
    call Claude and return the agent's next reply.

    Strips any [LOG_TICKET:...] tags before returning (those are handled separately).
    """
    client = _get_client()

    log.info(f"Sending {len(history)} message(s) to Claude...")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,  # Short responses for voice
        system=SYSTEM_PROMPT,
        messages=history,
    )

    raw_reply = response.content[0].text.strip()
    log.info(f"Raw Claude response: '{raw_reply}'")

    # Extract and handle ticket logging signal (future: wire to ticketing module)
    ticket_signal = None
    if "[LOG_TICKET:" in raw_reply:
        start = raw_reply.index("[LOG_TICKET:")
        end = raw_reply.index("]", start) + 1
        ticket_signal = raw_reply[start:end]
        raw_reply = raw_reply[:start].strip() + raw_reply[end:].strip()
        log.info(f"Ticket signal detected: {ticket_signal}")
        # TODO: call ticket_logger.log_ticket(ticket_signal) in Layer 6

    return raw_reply


# ---------------------------------------------------------------------------
# Quick local test — simulates a conversation without Twilio
# ---------------------------------------------------------------------------
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
