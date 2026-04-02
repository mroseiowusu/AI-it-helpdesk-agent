# IT Helpdesk Agent — Voice Pipeline (Layer 1)

## What this does

```
Caller dials your Twilio number
        ↓
Twilio POSTs to /voice/inbound
        ↓
Agent greets caller, opens <Gather> to listen
        ↓
Caller speaks → Twilio transcribes (or Whisper as fallback)
        ↓
Transcript → Claude API (with IT helpdesk system prompt)
        ↓
Claude's reply → Coqui TTS → WAV file served back to Twilio
        ↓
Caller hears the response, conversation continues
```

## Setup

### 1. Clone and install

```bash
pip install -r requirements.txt
```

> Also install ffmpeg for Whisper:
> - macOS: `brew install ffmpeg`
> - Ubuntu: `sudo apt install ffmpeg`
> - Windows: https://ffmpeg.org/download.html

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your ANTHROPIC_API_KEY and BASE_URL
```

### 3. Start the server

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Expose it with Ngrok

```bash
ngrok http 8000
```

Copy the HTTPS URL (e.g. `https://abc123.ngrok.io`) into your `.env` as `BASE_URL`,
then restart the server.

### 5. Configure Twilio

1. Go to [Twilio Console](https://console.twilio.com) → Phone Numbers → your number
2. Under **Voice Configuration**, set:
   - **Webhook (when a call comes in):** `https://YOUR_NGROK_URL/voice/inbound`
   - Method: `HTTP POST`
3. Save.

### 6. Test it

Call your Twilio number. You should hear the greeting and be able to have a
full back-and-forth conversation with the IT helpdesk agent.

## Test the agent logic without a phone call

```bash
# Test Claude reasoning in text mode
python agent.py

# Test TTS locally
python tts.py output.wav
# Then open output.wav in any audio player

# Test STT on a local file
python stt.py path/to/audio.wav
```

## File structure

```
voice_pipeline/
├── server.py          ← FastAPI server, Twilio webhook handlers
├── agent.py           ← Claude API integration, system prompt
├── stt.py             ← Whisper STT (local)
├── tts.py             ← Coqui TTS (local)
├── requirements.txt
├── .env.example
└── audio_cache/       ← Auto-created, stores TTS WAV files per session
```

## What's next (Layer 2+)

| Layer | What to add |
|-------|-------------|
| 2 | Wire `[LOG_TICKET:]` signal in `agent.py` to Jira/Linear API |
| 3 | SSH into user machine, pull `/var/log/syslog` or Windows Event Log |
| 4 | Screenshot capture via pyautogui + Pillow |
| 5 | Safe Windows registry reads via `winreg` |
| 6 | Auto-ticket creation with full conversation transcript attached |
| 7 | `.md` skill files loaded into Claude's context as dynamic runbooks |

## Troubleshooting

**Twilio can't reach my server**
→ Make sure Ngrok is running and `BASE_URL` in `.env` matches the current Ngrok URL.
  Ngrok URLs change each restart on the free tier — use `ngrok authtoken` for stable URLs.

**Audio sounds robotic**
→ Upgrade Coqui model in `tts.py` to `tts_models/en/vctk/vits` for more natural voice.

**Whisper is slow**
→ Twilio's own speech recognition (SpeechResult) handles most cases. Whisper is only
  used as a fallback for recordings. Use `model_size = "tiny"` in `stt.py` for speed.

**Claude gives too-long responses**
→ Adjust `max_tokens` in `agent.py`. 250–350 is the sweet spot for voice.
