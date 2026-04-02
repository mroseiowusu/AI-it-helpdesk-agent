import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent / "skills"

SKILL_KEYWORDS = {
    "vpn":            ["vpn", "virtual private network", "tunnel", "cisco", "globalprotect", "anyconnect", "disconnect"],
    "slow_computer":  ["slow", "sluggish", "freezing", "hanging", "frozen", "unresponsive", "high cpu", "memory", "ram", "lagging", "takes forever", "spinning"],
    "outlook":        ["outlook", "email", "mail", "inbox", "calendar", "sending", "receiving", "office", "microsoft mail"],
    "wifi":           ["wifi", "wi-fi", "wireless", "internet", "no connection", "network", "drops", "page not found", "internet explorer", "browser", "website"],
    "printer":        ["printer", "printing", "print", "scanner", "scan", "paper", "ink", "toner", "spooler"],
    "password_reset": ["password", "locked out", "cant login", "account locked", "reset", "forgot", "expired", "lockout", "credentials"],
}

def load_skill(skill_name: str) -> str | None:
    path = SKILLS_DIR / f"{skill_name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    log.warning(f"Skill file not found: {path}")
    return None

def match_skill(conversation_text: str) -> tuple[str, str] | tuple[None, None]:
    text_lower = conversation_text.lower()
    scores = {}
    for skill_name, keywords in SKILL_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[skill_name] = score
    if not scores:
        return None, None
    best_skill = max(scores, key=scores.get)
    content = load_skill(best_skill)
    if content:
        log.info(f"Matched skill: {best_skill} (score: {scores[best_skill]})")
        return best_skill, content
    return None, None

def get_skill_context(history: list[dict]) -> str | None:
    full_text = " ".join(msg["content"] for msg in history)
    skill_name, skill_content = match_skill(full_text)
    if not skill_content:
        return None
    return f"--- ACTIVE SKILL RUNBOOK: {skill_name.replace('_', ' ').upper()} ---\n{skill_content}\n--- END SKILL RUNBOOK ---"
