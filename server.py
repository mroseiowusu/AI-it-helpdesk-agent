import os
import logging
from fastapi import FastAPI, Request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather
from agent import get_agent_response

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="IT Helpdesk Voice Agent")
sessions: dict[str, list[dict]] = {}
BASE_URL = os.environ.get("BASE_URL", "")

def _speak_and_listen(text: str, action_url: str) -> str:
    vr = VoiceResponse()
    gather = Gather(input="speech", action=action_url, method="POST", speech_timeout="auto", language="en-US")
    gather.say(text, voice="Polly.Joanna")
    vr.append(gather)
    vr.redirect(action_url)
    return str(vr)

@app.post("/voice/inbound")
async def inbound_call(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    log.info(f"Inbound call: {call_sid}")
    sessions[call_sid] = []
    greeting = "Hello, this is the I T helpdesk assistant. Please describe your issue and I'll do my best to help."
    return Response(content=_speak_and_listen(greeting, f"{BASE_URL}/voice/respond"), media_type="application/xml")

@app.post("/voice/respond")
async def respond_to_caller(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    speech_result = form.get("SpeechResult", "").strip() or "(caller said nothing)"
    log.info(f"[{call_sid}] SpeechResult: '{speech_result}'")
    history = sessions.get(call_sid, [])
    history.append({"role": "user", "content": speech_result})
    agent_reply = get_agent_response(history)
    log.info(f"[{call_sid}] Agent: '{agent_reply}'")
    history.append({"role": "assistant", "content": agent_reply})
    sessions[call_sid] = history
    end_phrases = ["goodbye", "take care", "ticket has been logged", "have a great day"]
    if any(p in agent_reply.lower() for p in end_phrases):
        vr = VoiceResponse()
        vr.say(agent_reply, voice="Polly.Joanna")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")
    return Response(content=_speak_and_listen(agent_reply, f"{BASE_URL}/voice/respond"), media_type="application/xml")

@app.get("/health")
async def health():
    return {"status": "ok"}
