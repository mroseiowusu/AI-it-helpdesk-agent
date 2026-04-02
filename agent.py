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
- Spell out abbreviations on first use.

DIAGNOSTIC APPROACH:
1. Clarify the issue with one targeted question at a time.
2. Once you understand the problem, state your diagnosis clearly.
3. Walk the user through the fix step by step, one step per turn.
4. Confirm each step completed before moving to the next.
5. If you have remote access data available, reference it specifically.

REMOTE ACCESS:
- If diagnostic data from the user's machine is provided in the context, use it.
- Reference specific findings: "I can see your CPU is at 94 percent" not generic advice.
- If you need remote access and don't have it yet, signal with: [NEED_SSH: <host> <platform>]

SUPPORTED ISSUE CATEGORIES:
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
- When ending a call, always include: [LOG_TICKET: <one-line summary>]
- This tag will be stripped from the spoken response automatically.
"""


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY not set.")
        _client = Anthropic(api_key=api_key)
    return _client


def get_agent_response(history: list[dict], ssh_context: str = None) -> str:
    client = _get_client()

    messages = list(history)

    # Inject SSH diagnostic data if available
    if ssh_context:
        messages = [{"role": "user", "content": f"[REMOTE DIAGNOSTIC DATA FROM USER'S MACHINE]\n{ssh_context}\n[END DIAGNOSTIC DATA]"}] + messages

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    raw_reply = response.content[0].text.strip()
    log.info(f"Raw Claude response: '{raw_reply}'")

    # Handle SSH request signal
    if "[NEED_SSH:" in raw_reply:
        start = raw_reply.index("[NEED_SSH:")
        end = raw_reply.index("]", start) + 1
        ssh_signal = raw_reply[start+len("[NEED_SSH:"):-1].strip()
        raw_reply = (raw_reply[:start] + raw_reply[end:]).strip()
        log.info(f"SSH requested: {ssh_signal}")
        # Future: parse host/platform and trigger collect_diagnostics()

    # Handle ticket logging signal
    if "[LOG_TICKET:" in raw_reply:
        start = raw_reply.index("[LOG_TICKET:")
        end = raw_reply.index("]", start) + 1
        ticket_summary = raw_reply[start+len("[LOG_TICKET:"):-1].strip()
        raw_reply = (raw_reply[:start] + raw_reply[end:]).strip()
        log.info(f"Ticket signal: {ticket_summary}")
        try:
            from ticket_logger import log_ticket
            log_ticket(summary=ticket_summary, transcript=history)
        except Exception as e:
            log.error(f"Ticket logging failed: {e}")

    return raw_reply


if __name__ == "__main__":
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
