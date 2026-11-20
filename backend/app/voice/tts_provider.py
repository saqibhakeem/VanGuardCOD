"""Orpheus text-to-speech with a deterministic 200-character sentence chunker."""

from __future__ import annotations

import asyncio
import inspect
import io
import logging
import math
import re
import wave
from array import array
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import get_settings
from app.voice.audio import DEFAULT_SAMPLE_RATE, pcm16_to_wav

logger = logging.getLogger(__name__)

ORPHEUS_MAX_CHARS = 200

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_CLAUSE_BOUNDARY = re.compile(r"(?<=[,;:])\s+")


def _split_words(segment: str, max_len: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for word in segment.split():
        while len(word) > max_len:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(word[:max_len])
            word = word[max_len:]
        if not word:
            continue
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_len:
            current = f"{current} {word}"
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


def split_into_orpheus_chunks(text: str, max_len: int = ORPHEUS_MAX_CHARS) -> list[str]:
    """Split text into sentence and clause chunks that never exceed max_len."""

    if max_len < 1:
        raise ValueError("max_len must be at least 1")

    normalized = " ".join(text.split())
    if not normalized:
        return []

    chunks: list[str] = []
    for sentence in _SENTENCE_BOUNDARY.split(normalized):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= max_len:
            chunks.append(sentence)
            continue
        for clause in _CLAUSE_BOUNDARY.split(sentence):
            clause = clause.strip()
            if not clause:
                continue
            if len(clause) > max_len:
                chunks.extend(_split_words(clause, max_len))
                continue
            previous = chunks[-1] if chunks else ""
            can_merge = (
                previous
                and not previous.endswith((".", "!", "?"))
                and len(previous) + 1 + len(clause) <= max_len
            )
            if can_merge:
                chunks[-1] = f"{previous} {clause}"
            else:
                chunks.append(clause)

    return chunks


@dataclass(slots=True)
class SpeechChunk:
    text: str
    wav_bytes: bytes
    index: int


class TextToSpeech(Protocol):
    def stream_speech(
        self, text: str, *, voice: str | None = None
    ) -> AsyncIterator[SpeechChunk]: ...

    async def synthesize_speech(
        self, text: str, *, voice: str | None = None
    ) -> list[SpeechChunk]: ...


def _build_tone_wav(
    duration_ms: float = 60.0,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    frequency: float = 440.0,
    amplitude: int = 2800,
) -> bytes:
    frame_count = max(int(sample_rate * duration_ms / 1000), 1)
    samples = array(
        "h",
        (
            int(amplitude * math.sin(2 * math.pi * frequency * index / sample_rate))
            for index in range(frame_count)
        ),
    )
    return pcm16_to_wav(samples.tobytes(), sample_rate=sample_rate)


class _MockBinaryResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


class _MockSpeech:
    def __init__(self, client: "MockSpeechClient") -> None:
        self._client = client

    async def create(self, **kwargs: Any) -> _MockBinaryResponse:
        self._client.calls.append(kwargs)
        duration_ms = min(140.0, 40.0 + len(str(kwargs.get("input", ""))))
        payload = await asyncio.to_thread(_build_tone_wav, duration_ms)
        return _MockBinaryResponse(payload)


class _MockAudio:
    def __init__(self, client: "MockSpeechClient") -> None:
        self.speech = _MockSpeech(client)


class MockSpeechClient:
    """Deterministic AsyncGroq speech stand-in that returns valid tiny WAV clips."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.audio = _MockAudio(self)


async def _read_binary_response(response: Any) -> bytes:
    if isinstance(response, (bytes, bytearray)):
        return bytes(response)
    reader = getattr(response, "read", None)
    if reader is not None:
        payload = reader()
        if inspect.isawaitable(payload):
            payload = await payload
        return bytes(payload)
    content = getattr(response, "content", None)
    if content is not None:
        return bytes(content)
    raise TypeError("unsupported audio speech response object")


class GroqTextToSpeech:
    """Streams Orpheus WAV clauses while enforcing the 200-character guard."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        voice: str | None = None,
    ) -> None:
        settings = get_settings()
        self._client = client
        self.model = model or settings.tts_model
        self.voice = voice or settings.tts_default_voice

    def _get_client(self) -> Any:
        if self._client is None:
            settings = get_settings()
            if settings.mock_mode:
                self._client = MockSpeechClient()
            else:
                from groq import AsyncGroq

                self._client = AsyncGroq(api_key=settings.groq_api_key)
        return self._client

    async def _synthesize_chunk(self, text: str, voice: str) -> bytes:
        if len(text) > ORPHEUS_MAX_CHARS:
            raise ValueError(
                f"Orpheus input exceeds {ORPHEUS_MAX_CHARS} characters: {len(text)}"
            )
        try:
            response = await self._get_client().audio.speech.create(
                input=text,
                model=self.model,
                voice=voice,
                response_format="wav",
            )
            return await _read_binary_response(response)
        except Exception as exc:
            logger.warning(
                "Groq Orpheus TTS failed (%s: %s). Falling back to synthetic tone audio.",
                type(exc).__name__,
                exc,
            )
            duration_ms = min(140.0, 40.0 + len(text))
            return _build_tone_wav(duration_ms)

    async def synthesize_speech(
        self, text: str, *, voice: str | None = None
    ) -> list[SpeechChunk]:
        resolved_voice = voice or self.voice
        chunks = split_into_orpheus_chunks(text)
        return [
            SpeechChunk(
                text=chunk,
                wav_bytes=await self._synthesize_chunk(chunk, resolved_voice),
                index=index,
            )
            for index, chunk in enumerate(chunks)
        ]

    async def stream_speech(
        self, text: str, *, voice: str | None = None
    ) -> AsyncIterator[SpeechChunk]:
        resolved_voice = voice or self.voice
        chunks = split_into_orpheus_chunks(text)
        if not chunks:
            return

        next_synth: asyncio.Task[bytes] | None = asyncio.create_task(
            self._synthesize_chunk(chunks[0], resolved_voice)
        )
        for index, chunk in enumerate(chunks):
            wav_bytes = await next_synth
            if index + 1 < len(chunks):
                next_synth = asyncio.create_task(
                    self._synthesize_chunk(chunks[index + 1], resolved_voice)
                )
            else:
                next_synth = None
            yield SpeechChunk(text=chunk, wav_bytes=wav_bytes, index=index)


def wav_chunk_duration_ms(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate() or DEFAULT_SAMPLE_RATE
    return round(frames / rate * 1000, 3)
