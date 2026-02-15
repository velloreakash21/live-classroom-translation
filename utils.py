"""Audio format conversion utilities."""

import io
import wave
import numpy as np
from pydub import AudioSegment
from config import SAMPLE_RATE, FRAME_SIZE


def pcm_to_wav_bytes(pcm_data: np.ndarray, sample_rate: int = SAMPLE_RATE, channels: int = 1) -> bytes:
    """Convert PCM int16 numpy array to WAV bytes for Groq Whisper."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data.tobytes())
    buffer.seek(0)
    return buffer.read()


def mp3_bytes_to_pcm_frames(mp3_bytes: bytes, target_sample_rate: int = SAMPLE_RATE, frame_size: int = FRAME_SIZE) -> list:
    """Convert MP3 bytes from edge-tts to list of PCM chunks.

    Returns list of numpy int16 arrays, each of frame_size samples.
    """
    audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
    audio = audio.set_channels(1).set_frame_rate(target_sample_rate).set_sample_width(2)

    raw = np.frombuffer(audio.raw_data, dtype=np.int16)

    frames = []
    for i in range(0, len(raw), frame_size):
        chunk = raw[i:i + frame_size]
        if len(chunk) < frame_size:
            chunk = np.pad(chunk, (0, frame_size - len(chunk)), mode="constant")
        frames.append(chunk)

    return frames
