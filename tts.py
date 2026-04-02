"""
tts.py — Text-to-Speech using Coqui TTS (runs 100% locally)
============================================================
Coqui TTS produces natural-sounding speech without any API costs.

Install:
    pip install TTS

Model used here: tts_models/en/ljspeech/tacotron2-DDC
- Fast, decent quality, ~50MB
- For better voice quality, swap to: tts_models/en/vctk/vits (multi-speaker)

First run downloads the model automatically (~50-200MB).
"""

import logging
from pathlib import Path

log = logging.getLogger(__name__)

_tts_instance = None


def _get_tts():
    global _tts_instance
    if _tts_instance is None:
        # Import here to avoid slow startup if TTS not needed
        from TTS.api import TTS  # type: ignore
        model_name = "tts_models/en/ljspeech/tacotron2-DDC"
        log.info(f"Loading Coqui TTS model '{model_name}'...")
        _tts_instance = TTS(model_name=model_name, progress_bar=False, gpu=False)
        log.info("Coqui TTS model loaded.")
    return _tts_instance


def synthesize_speech(text: str, output_path: str) -> str:
    """
    Convert `text` to a WAV file at `output_path`.
    Returns the output path.

    Twilio requires audio to be accessible via HTTP — serve output_path
    through FastAPI's /audio/{filename} route.
    """
    log.info(f"Synthesizing TTS: '{text[:60]}...' → {output_path}")
    tts = _get_tts()
    tts.tts_to_file(text=text, file_path=output_path)
    log.info(f"TTS written to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Quick local test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    out = sys.argv[1] if len(sys.argv) > 1 else "test_output.wav"
    synthesize_speech(
        "Hello, this is the IT helpdesk assistant. How can I help you today?",
        out,
    )
    print(f"Audio written to {out}")
