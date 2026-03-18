"""
utils/voice_utils.py
Speech-to-Text (Whisper via OpenAI) and Text-to-Speech (gTTS fallback).
Handles audio bytes from Streamlit's file uploader / microphone widget.
"""

import io
import logging
import tempfile
import os
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)


# ── Speech to Text ────────────────────────────────────────────────────────────

def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/wav") -> Optional[str]:
    """
    Transcribe audio bytes to text using OpenAI Whisper.
    Falls back to a friendly message if OpenAI key is not set.
    """
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — voice transcription unavailable.")
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)

        # Write to a temp file (Whisper API needs a file object)
        suffix = ".wav" if "wav" in mime_type else ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="text",
                )
            text = transcript.strip() if isinstance(transcript, str) else transcript.text.strip()
            logger.info("Transcribed %d bytes → '%s'", len(audio_bytes), text[:80])
            return text
        finally:
            os.unlink(tmp_path)

    except Exception as exc:
        logger.error("Transcription failed: %s", exc)
        return None


# ── Text to Speech ────────────────────────────────────────────────────────────

def synthesize_speech(text: str, lang: str = "en") -> Optional[bytes]:
    """
    Convert text to speech audio bytes (MP3) using gTTS.
    Returns None if synthesis fails.
    """
    try:
        from gtts import gTTS

        tts = gTTS(text=text[:500], lang=lang, slow=False)  # cap at 500 chars
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        audio_bytes = buf.read()
        logger.debug("Synthesized %d bytes of speech.", len(audio_bytes))
        return audio_bytes
    except Exception as exc:
        logger.error("TTS synthesis failed: %s", exc)
        return None


def audio_bytes_to_base64(audio_bytes: bytes) -> str:
    """Return audio bytes as a base64 data-URI for embedding in HTML."""
    import base64
    encoded = base64.b64encode(audio_bytes).decode("utf-8")
    return f"data:audio/mp3;base64,{encoded}"
