"""Voice pipeline: Groq STT, Orpheus TTS, RMS VAD, and the audio session controller."""

from app.voice.audio import pcm16_duration_ms, pcm16_silence, pcm16_to_wav
from app.voice.session import AudioSessionController
from app.voice.stt_groq import (
    GroqSpeechToText,
    MockTranscriptionClient,
    TranscriptionResult,
)
from app.voice.tts_provider import (
    GroqTextToSpeech,
    MockSpeechClient,
    SpeechChunk,
    split_into_orpheus_chunks,
)
from app.voice.vad import RmsBargeInDetector, VadDecision, rms_energy

__all__ = [
    "AudioSessionController",
    "GroqSpeechToText",
    "GroqTextToSpeech",
    "MockSpeechClient",
    "MockTranscriptionClient",
    "RmsBargeInDetector",
    "SpeechChunk",
    "TranscriptionResult",
    "VadDecision",
    "pcm16_duration_ms",
    "pcm16_silence",
    "pcm16_to_wav",
    "rms_energy",
    "split_into_orpheus_chunks",
]
