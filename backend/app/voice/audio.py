"""PCM16 and WAV helpers shared by the voice pipeline and telephony adapters."""

from __future__ import annotations

import io
import wave

DEFAULT_SAMPLE_RATE = 16000
SAMPLE_WIDTH_BYTES = 2


def pcm16_to_wav(
    pcm_bytes: bytes,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = 1,
    sample_width: int = SAMPLE_WIDTH_BYTES,
) -> bytes:
    """Wrap raw little-endian PCM16 frames in an in-memory WAV container."""

    if sample_width != SAMPLE_WIDTH_BYTES:
        raise ValueError("only 16-bit PCM is supported")
    frame_size = sample_width * channels
    usable = len(pcm_bytes) - (len(pcm_bytes) % frame_size)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes[:usable])
    return buffer.getvalue()


def wav_frame_count(wav_bytes: bytes) -> int:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        return wav_file.getnframes()


def pcm16_duration_ms(pcm_bytes: bytes, *, sample_rate: int = DEFAULT_SAMPLE_RATE) -> float:
    sample_count = len(pcm_bytes) // SAMPLE_WIDTH_BYTES
    if sample_count == 0:
        return 0.0
    return round(sample_count / sample_rate * 1000, 3)


def pcm16_silence(duration_ms: float, *, sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes:
    sample_count = int(sample_rate * duration_ms / 1000)
    return b"\x00\x00" * max(sample_count, 0)
