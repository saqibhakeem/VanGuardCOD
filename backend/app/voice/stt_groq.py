"""Groq Whisper speech-to-text with in-memory WAV framing."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import get_settings
from app.voice.audio import DEFAULT_SAMPLE_RATE, pcm16_duration_ms, pcm16_to_wav

DEFAULT_TRANSCRIPT = "Yes, please confirm the order and deliver it tomorrow evening."


class SpeechToText(Protocol):
    async def transcribe_pcm_buffer(
        self,
        pcm_bytes: bytes,
        *,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        language: str | None = None,
    ) -> "TranscriptionResult": ...


@dataclass(slots=True)
class TranscriptionResult:
    text: str
    latency_ms: float
    model: str
    audio_ms: float = 0.0
    wav_bytes: int = 0


class _MockTranscription:
    def __init__(self, text: str) -> None:
        self.text = text


class _MockTranscriptions:
    def __init__(self, client: "MockTranscriptionClient") -> None:
        self._client = client

    async def create(self, **kwargs: Any) -> _MockTranscription:
        self._client.calls.append(kwargs)
        if self._client.script:
            return _MockTranscription(self._client.script.pop(0))
        return _MockTranscription(self._client.default_text)


class _MockAudio:
    def __init__(self, client: "MockTranscriptionClient") -> None:
        self.transcriptions = _MockTranscriptions(client)


class MockTranscriptionClient:
    """Deterministic AsyncGroq transcriptions stand-in for tests and demos."""

    def __init__(
        self,
        *,
        script: Sequence[str] | None = None,
        default_text: str = DEFAULT_TRANSCRIPT,
    ) -> None:
        self.script = list(script or [])
        self.default_text = default_text
        self.calls: list[dict[str, Any]] = []
        self.audio = _MockAudio(self)


class GroqSpeechToText:
    """Transcribes raw PCM16 buffers through Groq whisper-large-v3-turbo."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        language: str | None = None,
    ) -> None:
        settings = get_settings()
        self._client = client
        self.model = model or settings.stt_model
        self.sample_rate = sample_rate
        self.language = language if language is not None else (settings.stt_language or None)

    def _get_client(self) -> Any:
        if self._client is None:
            settings = get_settings()
            if settings.mock_mode:
                self._client = MockTranscriptionClient()
            else:
                from groq import AsyncGroq

                self._client = AsyncGroq(api_key=settings.groq_api_key)
        return self._client

    async def transcribe_pcm_buffer(
        self,
        pcm_bytes: bytes,
        *,
        sample_rate: int | None = None,
        language: str | None = None,
    ) -> TranscriptionResult:
        if not pcm_bytes:
            return TranscriptionResult(
                text="", latency_ms=0.0, model=self.model, audio_ms=0.0, wav_bytes=0
            )

        rate = sample_rate or self.sample_rate
        started = time.perf_counter()
        wav_bytes = await asyncio.to_thread(
            pcm16_to_wav, pcm_bytes, sample_rate=rate
        )
        audio_ms = pcm16_duration_ms(pcm_bytes, sample_rate=rate)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "file": ("audio.wav", wav_bytes, "audio/wav"),
            "response_format": "json",
        }
        resolved_language = language or self.language
        if resolved_language:
            kwargs["language"] = resolved_language

        response = await self._get_client().audio.transcriptions.create(**kwargs)
        text = getattr(response, "text", None)
        if text is None and isinstance(response, dict):
            text = response.get("text")
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return TranscriptionResult(
            text=str(text or "").strip(),
            latency_ms=latency_ms,
            model=self.model,
            audio_ms=audio_ms,
            wav_bytes=len(wav_bytes),
        )
