import os, re, logging, json
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

# WebSocket clients watching live calls
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
    sessions[call_sid] = {
        "history": [], "employee_id": None, "ssh_context": None,
        "awaiting_emp_id": True, "operator": False
    }
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

    # Dial 0 — transfer to operator
    if digits == "0":
        log.info(f"[{call_sid}] Caller pressed 0 — transferring to operator")
        await broadcast({"type": "operator_requested", "call_sid": call_sid})
        try:
            from ticket_logger import log_ticket
            session = sessions.get(call_sid, {})
            log_ticket(
                summary=f"Caller pressed 0 — escalated to human operator",
                transcript=session.get("history", []),
                priority="high"
            )
        except Exception as e:
            log.error(f"Ticket logging failed: {e}")
        return Response(content=_operator_twiml(), media_type="application/xml")

    session = sessions.get(call_sid, {
        "history": [], "employee_id": None, "ssh_context": None,
        "awaiting_emp_id": False, "operator": False
    })

    # Check if dashboard triggered operator takeover
    if session.get("operator"):
        return Response(content=_operator_twiml(), media_type="application/xml")

    if session.get("awaiting_emp_id"):
        emp_id = _parse_emp_id(speech_result)
        log.info(f"[{call_sid}] Parsed employee ID: {emp_id}")
        machine = get_machine(emp_id)
        if machine:
            session["employee_id"] = emp_id
            session["awaiting_emp_id"] = False
            await broadcast({"type": "emp_identified", "call_sid": call_sid, "emp_id": emp_id, "machine": machine["host"]})
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
            sessions[call_sid] = session
            return Response(content=_say(ack, f"{BASE_URL}/voice/respond"), media_type="application/xml")
        else:
            sessions[call_sid] = session
            retry = "I couldn't find that employee I D. Could you try again?"
            return Response(content=_say(retry, f"{BASE_URL}/voice/respond"), media_type="application/xml")

    history = session.get("history", [])
    history.append({"role": "user", "content": speech_result})
    await broadcast({"type": "transcript", "call_sid": call_sid, "role": "caller", "text": speech_result})

    # Inject any whisper from dashboard
    whisper = session.pop("whisper", None)
    ssh_ctx = session.get("ssh_context")
    if whisper:
        ssh_ctx = (ssh_ctx or "") + f"\n\n[OPERATOR HINT: {whisper}]"

    agent_reply = get_agent_response(history, ssh_context=ssh_ctx)
    log.info(f"[{call_sid}] Agent: '{agent_reply}'")
    history.append({"role": "assistant", "content": agent_reply})
    session["history"] = history
    sessions[call_sid] = session

    await broadcast({"type": "transcript", "call_sid": call_sid, "role": "agent", "text": agent_reply})

    if any(p in agent_reply.lower() for p in ["goodbye", "take care", "have a great day", "ticket has been logged"]):
        vr = VoiceResponse()
        vr.say(agent_reply, voice="Polly.Joanna")
        vr.hangup()
        await broadcast({"type": "call_end", "call_sid": call_sid})
        return Response(content=str(vr), media_type="application/xml")

    return Response(content=_say(agent_reply, f"{BASE_URL}/voice/respond"), media_type="application/xml")

@app.post("/voice/status")
async def call_status(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "")
    status = form.get("CallStatus", "")
    if status in ("completed", "failed", "busy", "no-answer"):
        sessions.pop(call_sid, None)
        await broadcast({"type": "call_end", "call_sid": call_sid})
    return Response(content="", status_code=204)

@app.post("/dashboard/takeover/{call_sid}")
async def takeover(call_sid: str):
    if call_sid in sessions:
        sessions[call_sid]["operator"] = True
        await broadcast({"type": "takeover", "call_sid": call_sid})
        if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and OPERATOR_PHONE:
            try:
                client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                client.calls(call_sid).update(
                    twiml=f'<Response><Say voice="Polly.Joanna">Connecting you to a live agent now.</Say><Dial>{OPERATOR_PHONE}</Dial></Response>'
                )
            except Exception as e:
                log.error(f"Twilio takeover failed: {e}")
    return {"status": "ok"}

@app.post("/dashboard/whisper/{call_sid}")
async def whisper(call_sid: str, request: Request):
    body = await request.json()
    if call_sid in sessions:
        sessions[call_sid]["whisper"] = body.get("message", "")
    return {"status": "ok"}

@app.websocket("/ws/calls")
async def websocket_calls(websocket: WebSocket):
    await websocket.accept()
    watchers.append(websocket)
    # Send current active calls
    active = [
        {"call_sid": sid, "emp_id": s.get("employee_id"), "history_len": len(s.get("history", []))}
        for sid, s in sessions.items()
    ]
    await websocket.send_text(json.dumps({"type": "init", "calls": active}))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in watchers:
            watchers.remove(websocket)


@app.get('/dashboard', response_class=HTMLResponse)
@app.get('/dashboard.html', response_class=HTMLResponse)
async def dashboard():
    from pathlib import Path
    f = Path(__file__).parent / 'dashboard.html'
    return f.read_text(encoding='utf-8')

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/voice/opt-in-consent-collector", response_class=HTMLResponse)
async def opt_in_consent():
    return """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>IT Helpdesk — SMS Consent</title><style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:600px;margin:60px auto;padding:0 24px;color:#1a1a1a}h1{font-size:22px;font-weight:600}p{font-size:15px;line-height:1.6;color:#444}.card{border:1px solid #e5e5e5;border-radius:12px;padding:28px;margin:24px 0}label{display:flex;align-items:flex-start;gap:12px;font-size:14px;color:#333;cursor:pointer}input[type=checkbox]{width:18px;height:18px;flex-shrink:0;margin-top:2px}.btn{display:block;width:100%;padding:14px;background:#1a1a1a;color:white;border:none;border-radius:8px;font-size:15px;font-weight:500;cursor:pointer;margin-top:20px;box-sizing:border-box}.fine{font-size:12px;color:#888;margin-top:16px;line-height:1.5}.badge{display:inline-block;background:#f0f0f0;border-radius:6px;padding:4px 10px;font-size:12px;color:#555;margin-bottom:20px}</style></head><body><span class="badge">IT Helpdesk Agent</span><h1>Stay updated on your support ticket</h1><p>By providing your phone number, you agree to receive SMS notifications from the IT Helpdesk Agent about your open tickets and resolutions.</p><div class="card"><label><input type="checkbox" id="consent"/><span>I agree to receive SMS messages from the IT Helpdesk team. Message and data rates may apply. Reply STOP to unsubscribe.</span></label><button class="btn" onclick="submit()">Confirm and continue</button><p class="fine">Message frequency varies. Reply HELP for help or STOP to cancel.</p></div><script>function submit(){if(!document.getElementById('consent').checked){alert('Please check the box first.');return;}var b=document.querySelector('.btn');b.textContent='Consent recorded. Thank you!';b.style.background='#2d6a2d';b.disabled=true;}</script></body></html>"""


@app.get("/api/tickets")
async def get_tickets():
    """Proxy Linear API to avoid CORS issues in dashboard"""
    import requests as req
    key = os.environ.get("LINEAR_API_KEY", "")
    query = """{ issues(filter:{team:{id:{eq:"5a834841-6f92-435f-bad9-4221bf3385ea"}}},orderBy:createdAt,last:50){nodes{id identifier title priority state{name}createdAt}}}"""
    try:
        r = req.post("https://api.linear.app/graphql",
            json={"query": query},
            headers={"Authorization": key, "Content-Type": "application/json"},
            timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}
