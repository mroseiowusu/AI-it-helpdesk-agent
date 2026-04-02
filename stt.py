"""
stt.py — Speech-to-Text using OpenAI Whisper (runs 100% locally)
=================================================================
Whisper model sizes: tiny / base / small / medium / large
- For a PoC on a laptop: "base" is fast and accurate enough
- For better accuracy on technical IT terms: bump to "small" or "medium"

Install:
    pip install openai-whisper
    # Also needs ffmpeg: brew install ffmpeg  |  sudo apt install ffmpeg
"""

import logging
import tempfile
from pathlib import Path

import whisper
import requests

log = logging.getLogger(__name__)

# Load model once at import time (cached on disk after first download)
_MODEL_NAME = "base"
_model = None


def _get_model():
    global _model
    if _model is None:
        log.info(f"Loading Whisper model '{_MODEL_NAME}'...")
        _model = whisper.load_model(_MODEL_NAME)
        log.info("Whisper model loaded.")
    return _model


def transcribe_audio(source: str) -> str:
    """
    Transcribe audio from either:
      - A local file path (str ending in .wav/.mp3/etc.)
      - A remote URL (Twilio recording URL)

    Returns the transcribed text string.
    """
    model = _get_model()

    # If it's a URL, download to a temp file first
    if source.startswith("http"):
        log.info(f"Downloading audio from URL: {source}")
        resp = requests.get(source, timeout=30)
        resp.raise_for_status()

        suffix = ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        log.info(f"Saved recording to temp file: {tmp_path}")
        source = tmp_path

    log.info(f"Transcribing: {source}")
    result = model.transcribe(source, language="en", fp16=False)
    transcript = result["text"].strip()
    log.info(f"Transcript: '{transcript}'")
    return transcript


# ---------------------------------------------------------------------------
# Quick local test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Usage: python stt.py <audio_file_or_url>")
        sys.exit(1)
    print(transcribe_audio(sys.argv[1]))
