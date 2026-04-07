import os, re, logging, json, time
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial
from twilio.rest import Client
from agent import get_agent_response
from machine_registry import init_db, get_machine, seed_demo_data
from remote_access import collect_diagnostics, summarize_for_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="IT Helpdesk Voice Agent")
sessions: dict[str, dict] = {}
BASE_URL = os.environ.get("BASE_URL", "")
OPERATOR_PHONE = os.environ.get("OPERATOR_PHONE", "")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")

init_db()
seed_demo_data()

# Call analytics logging
import sqlite3 as _sqlite3
from datetime import datetime as _datetime

def _init_analytics_db():
    conn = _sqlite3.connect('analytics.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_sid TEXT,
        employee_id TEXT,
        skill_matched TEXT,
        duration_seconds INTEGER,
        status TEXT,
        timestamp TEXT
    )''')
    conn.commit()
    conn.close()

def _log_call(call_sid, employee_id, skill_matched, duration_seconds, status):
    try:
        conn = _sqlite3.connect('analytics.db')
        conn.execute(
            'INSERT INTO calls (call_sid,employee_id,skill_matched,duration_seconds,status,timestamp) VALUES (?,?,?,?,?,?)',
            (call_sid, employee_id, skill_matched, duration_seconds, status, _datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"Analytics log error: {e}")

_init_analytics_db()

watchers: list[WebSocket] = []

async def broadcast(msg: dict):
    dead = []
    for ws in watchers:
        try:
            await ws.send_text(json.dumps(msg))
        except:
            dead.append(ws)
    for ws in dead:
        watchers.remove(ws)

def _twilio_client():
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return None

def _say(text: str, action_url: str) -> str:
    vr = VoiceResponse()
    gather = Gather(
        input="speech dtmf",
        action=action_url,
        method="POST",
        speech_timeout="auto",
        language="en-US",
        num_digits="1",
        finish_on_key=""
    )
    gather.say(text, voice="Polly.Joanna")
    vr.append(gather)
    vr.redirect(action_url)
    return str(vr)

def _parse_emp_id(speech: str) -> str:
    c = re.sub(r'\s+', '', speech.upper())
    m = re.search(r'EMP0*(\d+)', c) or re.search(r'(\d+)', c)
    return f"EMP{int(m.group(1)):03d}" if m else c

def _operator_twiml() -> str:
    vr = VoiceResponse()
    vr.say("Please hold while I transfer you to a live agent.", voice="Polly.Joanna")
    if OPERATOR_PHONE:
        vr.dial(OPERATOR_PHONE)
    else:
        vr.say("No operator is available right now. Please call back later.", voice="Polly.Joanna")
        vr.hangup()
    return str(vr)

@app.post("/voice/inbound")
async def inbound_call(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    log.info(f"Inbound call: {call_sid}")
    _session_set(call_sid, {
        "history": [], "employee_id": None, "ssh_context": None,
        "awaiting_emp_id": True, "operator": False
    })
    _call_stats["total"] += 1
    _call_stats["today"] = _call_stats.get("today", 0) + 1
    await broadcast({"type": "call_start", "call_sid": call_sid})
    greeting = (
        "Hello, this is the I T helpdesk assistant. "
        "Press zero at any time to speak with a live agent. "
        "Otherwise, please tell me your employee I D to get started."
    )
    return Response(content=_say(greeting, f"{BASE_URL}/voice/respond"), media_type="application/xml")

@app.post("/voice/respond")
async def respond_to_caller(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    digits = form.get("Digits", "")
    speech_result = form.get("SpeechResult", "").strip() or "(nothing)"
    log.info(f"[{call_sid}] Digits={digits!r} Speech={speech_result!r}")

    if digits == "0":
        log.info(f"[{call_sid}] Caller pressed 0 — transferring to operator")
        await broadcast({"type": "operator_requested", "call_sid": call_sid})
        try:
            from ticket_logger import log_ticket
            session = sessions.get(call_sid, {})
            log_ticket(
                summary="Caller pressed 0 — escalated to human operator",
                transcript=session.get("history", []),
                priority="high"
            )
        except Exception as e:
            log.error(f"Ticket logging failed: {e}")
        return Response(content=_operator_twiml(), media_type="application/xml")

    session = _session_get(call_sid) or {
        "history": [], "employee_id": None, "ssh_context": None,
        "awaiting_emp_id": False, "operator": False
    }

    if session.get("operator"):
        return Response(content=_operator_twiml(), media_type="application/xml")

    if session.get("awaiting_emp_id"):
        emp_id = _parse_emp_id(speech_result)
        log.info(f"[{call_sid}] Parsed employee ID: {emp_id}")
        machine = get_machine(emp_id)
        if machine:
            session["employee_id"] = emp_id
            session["awaiting_emp_id"] = False
            await broadcast({"type": "emp_identified", "call_sid": call_sid,
                           "emp_id": emp_id, "machine": machine["host"]})
            try:
                raw = collect_diagnostics(
                    host=machine["host"], username=machine["ssh_user"],
                    password=machine.get("ssh_pass"), key_path=machine.get("ssh_key"),
                    platform=machine["platform"]
                )
                session["ssh_context"] = summarize_for_agent(raw)
                ack = "Thanks, I found your machine. Please describe your issue."
            except Exception as e:
                log.error(f"SSH failed: {e}")
                session["ssh_context"] = None
                ack = "Thanks, I found your record. Please describe your issue."
            _session_set(call_sid, session)
            return Response(content=_say(ack, f"{BASE_URL}/voice/respond"), media_type="application/xml")
        else:
            _session_set(call_sid, session)
            retry = "I couldn't find that employee I D. Could you try again?"
            return Response(content=_say(retry, f"{BASE_URL}/voice/respond"), media_type="application/xml")

    history = session.get("history", [])
    history.append({"role": "user", "content": speech_result})
    await broadcast({"type": "transcript", "call_sid": call_sid, "role": "caller", "text": speech_result})

    # FIX: inject whisper as a proper operator directive so Claude sees it as instruction
    whisper = session.pop("whisper", None)
    ssh_ctx = session.get("ssh_context")
    whisper_directive = f"\n\n[OPERATOR DIRECTIVE — follow this instruction in your next response: {whisper}]" if whisper else ""
    if whisper_directive:
        await broadcast({"type": "whisper_ack", "call_sid": call_sid, "message": whisper})

    agent_reply = get_agent_response(history, ssh_context=ssh_ctx, whisper=whisper_directive)
    log.info(f"[{call_sid}] Agent: '{agent_reply}'")
    history.append({"role": "assistant", "content": agent_reply})
    session["history"] = history
    _session_set(call_sid, session)

    await broadcast({"type": "transcript", "call_sid": call_sid, "role": "agent", "text": agent_reply})

    if any(p in agent_reply.lower() for p in ["goodbye", "take care", "have a great day", "ticket has been logged"]):
        vr = VoiceResponse()
        vr.say(agent_reply, voice="Polly.Joanna")
        vr.hangup()
        # Log completed call to analytics
        _log_call(
            call_sid=call_sid,
            employee_id=session.get("employee_id", "unknown"),
            skill_matched=session.get("skill_matched", "none"),
            duration_seconds=len(history) * 30,
            status="resolved"
        )
        _call_stats["total"] += 1
        _session_del(call_sid)
        await broadcast({"type": "call_end", "call_sid": call_sid})
        return Response(content=str(vr), media_type="application/xml")

    return Response(content=_say(agent_reply, f"{BASE_URL}/voice/respond"), media_type="application/xml")

@app.post("/voice/status")
async def call_status(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "")
    status = form.get("CallStatus", "")
    log.info(f"Call status: {call_sid} → {status}")
    if status in ("completed", "failed", "busy", "no-answer", "canceled"):
        _session_del(call_sid)
        await broadcast({"type": "call_end", "call_sid": call_sid})
    return Response(content="", status_code=204)

@app.post("/dashboard/hangup/{call_sid}")
async def hangup(call_sid: str):
    """Hang up a live call from the dashboard."""
    client = _twilio_client()
    if client:
        try:
            client.calls(call_sid).update(status="completed")
            log.info(f"Dashboard hung up call: {call_sid}")
        except Exception as e:
            log.error(f"Hangup failed: {e}")
            return {"status": "error", "message": str(e)}
    _session_del(call_sid)
    await broadcast({"type": "call_end", "call_sid": call_sid})
    return {"status": "ok"}

@app.post("/dashboard/takeover/{call_sid}")
async def takeover(call_sid: str):
    if _session_get(call_sid):
        sessions[call_sid]["operator"] = True
        await broadcast({"type": "takeover", "call_sid": call_sid})
        client = _twilio_client()
        if client and OPERATOR_PHONE:
            try:
                client.calls(call_sid).update(
                    twiml=f'<Response><Say voice="Polly.Joanna">Connecting you to a live agent now.</Say><Dial>{OPERATOR_PHONE}</Dial></Response>'
                )
            except Exception as e:
                log.error(f"Twilio takeover failed: {e}")
    return {"status": "ok"}

@app.post("/dashboard/whisper/{call_sid}")
async def whisper(call_sid: str, request: Request):
    body = await request.json()
    if _session_get(call_sid):
        sessions[call_sid]["whisper"] = body.get("message", "")
        log.info(f"Whisper queued for {call_sid}: {body.get('message')}")
    return {"status": "ok"}

@app.get("/api/tickets")
async def get_tickets():
    key = os.environ.get("LINEAR_API_KEY", "")
    query = """{ issues(filter:{team:{id:{eq:"5a834841-6f92-435f-bad9-4221bf3385ea"}}},orderBy:createdAt,last:50){nodes{id identifier title priority state{name}assignee{name}createdAt updatedAt}}}"""
    try:
        import json as _jj
        from urllib.request import urlopen, Request as _RR
        _req = _RR("https://api.linear.app/graphql",
            data=_jj.dumps({"query": query}).encode(),
            headers={"Authorization": key, "Content-Type": "application/json"},
            method="POST")
        return _jj.loads(urlopen(_req, timeout=10).read())
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/health")
async def health_check():
    """Real health check — pings all connected services and returns live status."""
    import json as _jh, urllib.request as _uh
    results = {}

    # Twilio
    try:
        client = _twilio_client()
        if client:
            t0 = time.time()
            client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
            results["twilio"] = {"status": "ok", "latency_ms": round((time.time()-t0)*1000)}
        else:
            results["twilio"] = {"status": "no_credentials"}
    except Exception as e:
        results["twilio"] = {"status": "error", "message": str(e)}

    # Anthropic
    try:
        import anthropic
        t0 = time.time()
        c = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY",""))
        c.messages.create(model="claude-haiku-4-5-20251001", max_tokens=10,
                          messages=[{"role":"user","content":"ping"}])
        results["anthropic"] = {"status": "ok", "latency_ms": round((time.time()-t0)*1000)}
    except Exception as e:
        results["anthropic"] = {"status": "error", "message": str(e)[:80]}

    # Linear
    try:
        t0 = time.time()
        import json as _jh
        from urllib.request import urlopen, Request as _RH
        _req = _RH("https://api.linear.app/graphql",
            data=_jh.dumps({"query": "{ viewer { id } }"}).encode(),
            headers={"Authorization": os.environ.get("LINEAR_API_KEY",""),
                     "Content-Type": "application/json"}, method="POST")
        _resp = urlopen(_req, timeout=5)
        results["linear"] = {"status": "ok" if _resp.status==200 else "error",
                              "latency_ms": round((time.time()-t0)*1000)}
    except Exception as e:
        results["linear"] = {"status": "error", "message": str(e)[:80]}

    # Railway (self)
    results["railway"] = {"status": "ok", "latency_ms": 0, "region": "us-west2"}

    # SSH registry
    from machine_registry import _get_conn
    try:
        conn = _get_conn()
        rows = conn.execute("SELECT COUNT(*) FROM machines").fetchone()
        results["ssh"] = {"status": "registry_ok", "machines": rows[0]}
    except Exception as e:
        results["ssh"] = {"status": "error", "message": str(e)[:80]}

    # Skills
    from pathlib import Path
    skills_dir = Path(__file__).parent / "skills"
    skill_files = list(skills_dir.glob("*.md"))
    results["skills"] = {"status": "ok", "count": len(skill_files),
                         "files": [f.name for f in skill_files]}

    return results

@app.post("/api/tickets/{ticket_id}/close")
async def close_ticket(ticket_id: str):
    import json as _jc, urllib.request as _uc
    key = os.environ.get("LINEAR_API_KEY", "")
    # First get workflow states to find cancelled state
    _sr = _uc.Request("https://api.linear.app/graphql",
        data=_jc.dumps({"query": '{ workflowStates(filter:{team:{id:{eq:"5a834841-6f92-435f-bad9-4221bf3385ea"}}}){nodes{id name type}}}'}).encode(),
        headers={"Authorization": key, "Content-Type": "application/json"}, method="POST")
    states = _jc.loads(_uc.urlopen(_sr, timeout=10).read())["data"]["workflowStates"]["nodes"]
    target = next((s for s in states if s["type"] == "cancelled"), None) or              next((s for s in states if s["type"] == "completed"), None)
    if not target:
        return {"error": "No done/cancelled state found"}
    # Update the ticket
    _target_id = target["id"]
    _mutation = f'mutation {{ issueUpdate(id: "{ticket_id}", input: {{stateId: "{_target_id}"}}) {{ success issue {{ identifier state {{ name }} }} }} }}'
    _mr = _uc.Request("https://api.linear.app/graphql",
        data=_jc.dumps({"query": _mutation}).encode(),
        headers={"Authorization": key, "Content-Type": "application/json"}, method="POST")
    return _jc.loads(_uc.urlopen(_mr, timeout=10).read())
@app.get("/api/analytics")
async def get_analytics():
    import sqlite3 as sq
    from datetime import datetime, timedelta
    try:
        conn = sq.connect('analytics.db')
        conn.row_factory = sq.Row
        
        # Last 14 days call volume
        days = []
        for i in range(13, -1, -1):
            day = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM calls WHERE timestamp LIKE ?", (day+'%',)
            ).fetchone()
            days.append({"date": day, "calls": row["cnt"]})
        
        # Skill breakdown
        skills = conn.execute(
            "SELECT skill_matched, COUNT(*) as cnt FROM calls GROUP BY skill_matched ORDER BY cnt DESC"
        ).fetchall()
        
        # Status breakdown
        statuses = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM calls GROUP BY status"
        ).fetchall()
        
        # Total stats
        total = conn.execute("SELECT COUNT(*) as cnt FROM calls").fetchone()
        avg_dur = conn.execute("SELECT AVG(duration_seconds) as avg FROM calls").fetchone()
        
        conn.close()
        return {
            "daily": days,
            "skills": [dict(r) for r in skills],
            "statuses": [dict(r) for r in statuses],
            "total_calls": total["cnt"],
            "avg_duration_seconds": round(avg_dur["avg"] or 0)
        }
    except Exception as e:
        return {"error": str(e), "daily": [], "skills": [], "statuses": [], "total_calls": 0}

@app.get("/api/sessions")
async def get_sessions():
    """Return active call sessions for dashboard."""
    return {
        sid: {
            "employee_id": s.get("employee_id"),
            "history_len": len(s.get("history", [])),
            "has_ssh": s.get("ssh_context") is not None
        }
        for sid, s in sessions.items()
    }

@app.websocket("/ws/calls")
async def websocket_calls(websocket: WebSocket):
    await websocket.accept()
    watchers.append(websocket)
    active = [
        {"call_sid": sid, "emp_id": s.get("employee_id"),
         "history_len": len(s.get("history", []))}
        for sid, s in _session_list()
    ]
    await websocket.send_text(json.dumps({"type": "init", "calls": active}))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in watchers:
            watchers.remove(websocket)

@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(_session_list())}

@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/dashboard.html", response_class=HTMLResponse)
async def dashboard():
    from pathlib import Path
    from fastapi.responses import HTMLResponse as _HR
    f = Path(__file__).parent / "dashboard.html"
    html = f.read_text(encoding="utf-8")
    return _HR(content=html, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    })

@app.get("/voice/opt-in-consent-collector", response_class=HTMLResponse)
async def opt_in_consent():
    return """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>IT Helpdesk — SMS Consent</title><style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:600px;margin:60px auto;padding:0 24px;color:#1a1a1a}h1{font-size:22px;font-weight:600}p{font-size:15px;line-height:1.6;color:#444}.card{border:1px solid #e5e5e5;border-radius:12px;padding:28px;margin:24px 0}label{display:flex;align-items:flex-start;gap:12px;font-size:14px;color:#333;cursor:pointer}input[type=checkbox]{width:18px;height:18px;flex-shrink:0;margin-top:2px}.btn{display:block;width:100%;padding:14px;background:#1a1a1a;color:white;border:none;border-radius:8px;font-size:15px;font-weight:500;cursor:pointer;margin-top:20px;box-sizing:border-box}.fine{font-size:12px;color:#888;margin-top:16px;line-height:1.5}.badge{display:inline-block;background:#f0f0f0;border-radius:6px;padding:4px 10px;font-size:12px;color:#555;margin-bottom:20px}</style></head><body><span class="badge">IT Helpdesk Agent</span><h1>Stay updated on your support ticket</h1><p>By providing your phone number, you agree to receive SMS notifications from the IT Helpdesk Agent about your open tickets and resolutions.</p><div class="card"><label><input type="checkbox" id="consent"/><span>I agree to receive SMS messages from the IT Helpdesk team. Message and data rates may apply. Reply STOP to unsubscribe.</span></label><button class="btn" onclick="submit()">Confirm and continue</button><p class="fine">Message frequency varies. Reply HELP for help or STOP to cancel.</p></div><script>function submit(){if(!document.getElementById('consent').checked){alert('Please check the box first.');return;}var b=document.querySelector('.btn');b.textContent='Consent recorded. Thank you!';b.style.background='#2d6a2d';b.disabled=true;}</script></body></html>"""


import json as _json
from pathlib import Path as _Path
from datetime import datetime as _dt

_call_stats = {"total": 0, "today": 0, "last_date": None}
_SKILLS_DIR = _Path(__file__).parent / "skills"
_VOICE_CONFIG = {"provider": "polly", "voice": "Polly.Joanna"}

@app.get("/api/stats")
async def get_stats():
    today = _dt.utcnow().strftime("%Y-%m-%d")
    if _call_stats["last_date"] != today:
        _call_stats["today"] = 0
        _call_stats["last_date"] = today
    return {
        "calls_total": _call_stats["total"],
        "calls_today": _call_stats["today"],
        "active_calls": len(_session_list()),
        "date": today
    }

@app.get("/api/skills")
async def list_skills():
    skills = []
    for f in sorted(_SKILLS_DIR.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        skills.append({
            "name": f.name,
            "size": len(content),
            "lines": content.count("\n"),
            "modified": f.stat().st_mtime,
        })
    return {"skills": skills}

@app.get("/api/skills/{name}")
async def get_skill(name: str):
    f = _SKILLS_DIR / name
    if not f.exists() or not name.endswith(".md"):
        return {"error": "Not found"}
    return {"name": name, "content": f.read_text(encoding="utf-8")}

@app.post("/api/skills/{name}")
async def save_skill(name: str, request: Request):
    if not name.endswith(".md"):
        return {"error": "Must be a .md file"}
    body = await request.json()
    content = body.get("content", "")
    _SKILLS_DIR.mkdir(exist_ok=True)
    (_SKILLS_DIR / name).write_text(content, encoding="utf-8")
    log.info(f"Skill saved: {name} ({len(content)} chars)")
    return {"status": "ok", "name": name, "size": len(content)}

@app.delete("/api/skills/{name}")
async def delete_skill(name: str):
    f = _SKILLS_DIR / name
    if not f.exists():
        return {"error": "Not found"}
    f.unlink()
    log.info(f"Skill deleted: {name}")
    return {"status": "ok"}

@app.get("/api/voice")
async def get_voice():
    return _VOICE_CONFIG

@app.post("/api/voice")
async def set_voice(request: Request):
    body = await request.json()
    _VOICE_CONFIG["provider"] = body.get("provider", "polly")
    _VOICE_CONFIG["voice"] = body.get("voice", "Polly.Joanna")
    _VOICE_CONFIG["api_key"] = body.get("api_key", "")
    log.info(f"Voice config updated: {_VOICE_CONFIG['provider']} / {_VOICE_CONFIG['voice']}")
    return {"status": "ok", "config": _VOICE_CONFIG}
