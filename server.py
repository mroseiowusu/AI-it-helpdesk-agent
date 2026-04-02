import os, re, logging
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from twilio.twiml.voice_response import VoiceResponse, Gather
from agent import get_agent_response
from machine_registry import init_db, get_machine, seed_demo_data
from remote_access import collect_diagnostics, summarize_for_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="IT Helpdesk Voice Agent")
sessions: dict[str, dict] = {}
BASE_URL = os.environ.get("BASE_URL", "")

init_db()
seed_demo_data()

def _say(text: str, action_url: str) -> str:
    vr = VoiceResponse()
    gather = Gather(input="speech", action=action_url, method="POST",
                    speech_timeout="auto", language="en-US")
    gather.say(text, voice="Polly.Joanna")
    vr.append(gather)
    vr.redirect(action_url)
    return str(vr)

def _parse_emp_id(speech: str) -> str:
    c = re.sub(r'\s+', '', speech.upper())
    m = re.search(r'EMP0*(\d+)', c) or re.search(r'(\d+)', c)
    return f"EMP{int(m.group(1)):03d}" if m else c

@app.post("/voice/inbound")
async def inbound_call(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    log.info(f"Inbound call: {call_sid}")
    sessions[call_sid] = {"history": [], "employee_id": None, "ssh_context": None, "awaiting_emp_id": True}
    greeting = "Hello, this is the I T helpdesk assistant. Before I help you, can I get your employee I D please? For example, say E M P zero zero one."
    return Response(content=_say(greeting, f"{BASE_URL}/voice/respond"), media_type="application/xml")

@app.post("/voice/respond")
async def respond_to_caller(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    speech_result = form.get("SpeechResult", "").strip() or "(nothing)"
    log.info(f"[{call_sid}] Heard: '{speech_result}'")
    session = sessions.get(call_sid, {"history": [], "employee_id": None, "ssh_context": None, "awaiting_emp_id": False})

    if session.get("awaiting_emp_id"):
        emp_id = _parse_emp_id(speech_result)
        log.info(f"[{call_sid}] Parsed employee ID: {emp_id}")
        machine = get_machine(emp_id)
        if machine:
            session["employee_id"] = emp_id
            session["awaiting_emp_id"] = False
            try:
                raw = collect_diagnostics(host=machine["host"], username=machine["ssh_user"],
                                          password=machine.get("ssh_pass"), key_path=machine.get("ssh_key"),
                                          platform=machine["platform"])
                session["ssh_context"] = summarize_for_agent(raw)
                ack = "Thanks, I found your machine and pulled your system diagnostics. Please describe your issue."
            except Exception as e:
                log.error(f"SSH failed: {e}")
                session["ssh_context"] = None
                ack = "Thanks, I found your record. Please describe your issue and I'll do my best to help."
            sessions[call_sid] = session
            return Response(content=_say(ack, f"{BASE_URL}/voice/respond"), media_type="application/xml")
        else:
            log.info(f"[{call_sid}] No machine found for: {emp_id}")
            sessions[call_sid] = session
            retry = "I couldn't find an employee with that I D. Could you try again? Please say your employee I D clearly, for example E M P zero zero one."
            return Response(content=_say(retry, f"{BASE_URL}/voice/respond"), media_type="application/xml")

    history = session.get("history", [])
    history.append({"role": "user", "content": speech_result})
    agent_reply = get_agent_response(history, ssh_context=session.get("ssh_context"))
    log.info(f"[{call_sid}] Agent: '{agent_reply}'")
    history.append({"role": "assistant", "content": agent_reply})
    session["history"] = history
    sessions[call_sid] = session

    if any(p in agent_reply.lower() for p in ["goodbye", "take care", "have a great day", "ticket has been logged"]):
        vr = VoiceResponse()
        vr.say(agent_reply, voice="Polly.Joanna")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

    return Response(content=_say(agent_reply, f"{BASE_URL}/voice/respond"), media_type="application/xml")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/voice/opt-in-consent-collector", response_class=HTMLResponse)
async def opt_in_consent():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>IT Helpdesk — SMS Consent</title>
  <style>
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:600px;margin:60px auto;padding:0 24px;color:#1a1a1a}
    h1{font-size:22px;font-weight:600}p{font-size:15px;line-height:1.6;color:#444}
    .card{border:1px solid #e5e5e5;border-radius:12px;padding:28px;margin:24px 0}
    label{display:flex;align-items:flex-start;gap:12px;font-size:14px;color:#333;cursor:pointer}
    input[type=checkbox]{width:18px;height:18px;flex-shrink:0;margin-top:2px}
    .btn{display:block;width:100%;padding:14px;background:#1a1a1a;color:white;border:none;border-radius:8px;font-size:15px;font-weight:500;cursor:pointer;margin-top:20px;box-sizing:border-box}
    .fine{font-size:12px;color:#888;margin-top:16px;line-height:1.5}
    .badge{display:inline-block;background:#f0f0f0;border-radius:6px;padding:4px 10px;font-size:12px;color:#555;margin-bottom:20px}
  </style>
</head>
<body>
  <span class="badge">IT Helpdesk Agent</span>
  <h1>Stay updated on your support ticket</h1>
  <p>By providing your phone number, you agree to receive SMS notifications from the IT Helpdesk Agent about your open tickets and resolutions.</p>
  <div class="card">
    <label><input type="checkbox" id="consent"/>
    <span>I agree to receive SMS messages from the IT Helpdesk team. Message and data rates may apply. Reply STOP to unsubscribe.</span></label>
    <button class="btn" onclick="submit()">Confirm and continue</button>
    <p class="fine">Message frequency varies. Reply HELP for help or STOP to cancel.</p>
  </div>
  <script>
    function submit(){
      if(!document.getElementById('consent').checked){alert('Please check the box first.');return;}
      var b=document.querySelector('.btn');b.textContent='Consent recorded. Thank you!';b.style.background='#2d6a2d';b.disabled=true;
    }
  </script>
</body>
</html>"""
