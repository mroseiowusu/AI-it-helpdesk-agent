"""
IT Helpdesk Agent — Voice Pipeline (Layer 1)
=============================================
Flow: Twilio call → Whisper STT → Claude reasoning → Coqui TTS → caller hears response

Run with:
    uvicorn server:app --host 0.0.0.0 --port 8000 --reload

Expose locally with:
    ngrok http 8000
Then set your Twilio webhook to: https://<ngrok-id>.ngrok.io/voice/inbound
"""

import os
import uuid
import logging
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from twilio.twiml.voice_response import VoiceResponse, Gather

from stt import transcribe_audio
from tts import synthesize_speech
from agent import get_agent_response

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="IT Helpdesk Voice Agent")

# Directory to serve generated TTS audio files
AUDIO_DIR = Path("audio_cache")
AUDIO_DIR.mkdir(exist_ok=True)

# In-memory session store (swap for Redis/SQLite in production)
sessions: dict[str, list[dict]] = {}


# ---------------------------------------------------------------------------
# Helper: build a TwiML response that speaks text and then listens
# ---------------------------------------------------------------------------
def _speak_and_listen(text: str, action_url: str, session_id: str) -> str:
    """
    Synthesize `text` to a WAV file, return TwiML that:
      1. Plays the audio
      2. Opens a <Gather> to capture the caller's next utterance
    """
    filename = f"{session_id}_{uuid.uuid4().hex[:8]}.wav"
    audio_path = AUDIO_DIR / filename
    synthesize_speech(text, str(audio_path))

    vr = VoiceResponse()
    # Play the synthesized audio
    audio_url = f"{os.environ['BASE_URL']}/audio/{filename}"
    gather = Gather(
        input="speech",
        action=action_url,
        method="POST",
        speech_timeout="auto",
        language="en-US",
    )
    gather.play(audio_url)
    vr.append(gather)

    # Fallback if caller says nothing
    vr.redirect(action_url)
    return str(vr)


# ---------------------------------------------------------------------------
# Route 1: Inbound call — greet the caller
# ---------------------------------------------------------------------------
@app.post("/voice/inbound")
async def inbound_call(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    log.info(f"Inbound call: {call_sid}")

    # Create a fresh session
    sessions[call_sid] = []

    greeting = (
        "Hello, this is the IT helpdesk assistant. "
        "Please describe your issue and I'll do my best to help."
    )
    twiml = _speak_and_listen(
        text=greeting,
        action_url=f"{os.environ['BASE_URL']}/voice/respond",
        session_id=call_sid,
    )
    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Route 2: Caller has spoken — STT → Agent → TTS → respond
# ---------------------------------------------------------------------------
@app.post("/voice/respond")
async def respond_to_caller(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    speech_result = form.get("SpeechResult", "").strip()
    recording_url = form.get("RecordingUrl")  # present if using <Record> instead

    log.info(f"[{call_sid}] SpeechResult: '{speech_result}'")

    # --- STT fallback: if Twilio didn't transcribe, use Whisper on the recording ---
    if not speech_result and recording_url:
        log.info(f"[{call_sid}] Falling back to Whisper STT on recording")
        speech_result = transcribe_audio(recording_url)

    if not speech_result:
        speech_result = "(caller said nothing)"

    # --- Build conversation history ---
    history = sessions.get(call_sid, [])
    history.append({"role": "user", "content": speech_result})

    # --- Get AI response ---
    agent_reply = get_agent_response(history)
    log.info(f"[{call_sid}] Agent: '{agent_reply}'")

    history.append({"role": "assistant", "content": agent_reply})
    sessions[call_sid] = history

    # --- Detect call-ending phrases ---
    lower_reply = agent_reply.lower()
    end_phrases = ["goodbye", "take care", "ticket has been logged", "have a great day"]
    is_ending = any(p in lower_reply for p in end_phrases)

    if is_ending:
        # Speak farewell and hang up
        filename = f"{call_sid}_farewell.wav"
        audio_path = AUDIO_DIR / filename
        synthesize_speech(agent_reply, str(audio_path))

        vr = VoiceResponse()
        vr.play(f"{os.environ['BASE_URL']}/audio/{filename}")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

    # --- Continue the conversation ---
    twiml = _speak_and_listen(
        text=agent_reply,
        action_url=f"{os.environ['BASE_URL']}/voice/respond",
        session_id=call_sid,
    )
    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Route 3: Serve generated audio files to Twilio
# ---------------------------------------------------------------------------
@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    path = AUDIO_DIR / filename
    if not path.exists():
        return Response(status_code=404)
    return FileResponse(str(path), media_type="audio/wav")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}
