"""Translation pipeline: Groq STT -> Groq Translation -> edge-tts synthesis."""

import io
import logging
import asyncio
import edge_tts
from groq import Groq
from config import STT_MODEL, TRANSLATION_MODEL

logger = logging.getLogger(__name__)


def transcribe(wav_bytes: bytes, api_key: str) -> str:
    """Transcribe WAV audio bytes to English text using Groq Whisper."""
    try:
        client = Groq(api_key=api_key)
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "audio.wav"
        transcription = client.audio.transcriptions.create(
            model=STT_MODEL,
            file=audio_file,
            language="en",
        )
        text = transcription.text.strip()
        logger.info(f"Transcribed: {text[:100]}")
        return text
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return ""


def translate(text: str, target_language: str, api_key: str) -> str:
    """Translate English text to target language using Groq Llama3."""
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=TRANSLATION_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a professional translator. Translate the following English text "
                        f"to {target_language}. Return ONLY the translated text, nothing else. "
                        f"No explanations, no notes, no original text."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.3,
            max_tokens=1024,
        )
        translated = response.choices[0].message.content.strip()
        logger.info(f"Translated to {target_language}: {translated[:100]}")
        return translated
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        return ""


def synthesize(text: str, voice_id: str) -> bytes:
    """Convert text to speech using edge-tts."""
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_synthesize_async(text, voice_id))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        return b""


async def _synthesize_async(text: str, voice_id: str) -> bytes:
    """Async implementation of text-to-speech synthesis."""
    communicate = edge_tts.Communicate(text, voice_id)
    buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buffer.write(chunk["data"])
    buffer.seek(0)
    return buffer.read()
