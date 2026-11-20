"""RMS energy barge-in detection and utterance finalization for PCM16 frames."""

from __future__ import annotations

import math
import sys
from array import array
from dataclasses import dataclass, field

from app.voice.audio import DEFAULT_SAMPLE_RATE, pcm16_duration_ms

DEFAULT_FRAME_MS = 20.0
DEFAULT_SPEECH_THRESHOLD = 300.0
DEFAULT_SILENCE_THRESHOLD = 120.0
DEFAULT_SPEECH_FRAMES_TO_TRIGGER = 3
DEFAULT_SILENCE_MS_TO_FINALIZE = 450.0
DEFAULT_MAX_UTTERANCE_MS = 30000.0


def rms_energy(pcm_bytes: bytes) -> float:
    """Return the root mean square amplitude of little-endian PCM16 samples."""

    usable = len(pcm_bytes) - (len(pcm_bytes) % 2)
    if usable == 0:
        return 0.0
    samples = array("h")
    samples.frombytes(pcm_bytes[:usable])
    if sys.byteorder != "little":
        samples.byteswap()
    total = 0
    for sample in samples:
        total += sample * sample
    return math.sqrt(total / len(samples))


@dataclass(slots=True)
class VadDecision:
    rms: float
    is_speech: bool
    is_silence: bool
    barge_in: bool = False
    speech_finalized: bool = False
    truncated: bool = False
    buffered_pcm: bytes = b""


@dataclass(slots=True)
class RmsBargeInDetector:
    """Stateful VAD that triggers barge-in and finalizes utterances on silence."""

    sample_rate: int = DEFAULT_SAMPLE_RATE
    speech_threshold: float = DEFAULT_SPEECH_THRESHOLD
    silence_threshold: float = DEFAULT_SILENCE_THRESHOLD
    speech_frames_to_trigger: int = DEFAULT_SPEECH_FRAMES_TO_TRIGGER
    silence_ms_to_finalize: float = DEFAULT_SILENCE_MS_TO_FINALIZE
    max_utterance_ms: float = DEFAULT_MAX_UTTERANCE_MS
    frame_ms: float = DEFAULT_FRAME_MS
    _speech_run: int = field(default=0, init=False, repr=False)
    _silence_ms: float = field(default=0.0, init=False, repr=False)
    _utterance_ms: float = field(default=0.0, init=False, repr=False)
    _in_utterance: bool = field(default=False, init=False, repr=False)
    _barge_in_latched: bool = field(default=False, init=False, repr=False)
    _buffer: bytearray = field(default_factory=bytearray, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.silence_threshold >= self.speech_threshold:
            raise ValueError("silence_threshold must be lower than speech_threshold")
        if self.speech_frames_to_trigger < 1:
            raise ValueError("speech_frames_to_trigger must be at least 1")
        if self.silence_ms_to_finalize <= 0:
            raise ValueError("silence_ms_to_finalize must be positive")
        if self.max_utterance_ms <= 0:
            raise ValueError("max_utterance_ms must be positive")

    def reset(self) -> None:
        self._speech_run = 0
        self._silence_ms = 0.0
        self._utterance_ms = 0.0
        self._in_utterance = False
        self._barge_in_latched = False
        self._buffer.clear()

    def process_frame(self, pcm_bytes: bytes, *, agent_speaking: bool) -> VadDecision:
        rms = rms_energy(pcm_bytes)
        duration_ms = pcm16_duration_ms(pcm_bytes, sample_rate=self.sample_rate) or self.frame_ms
        is_speech = rms >= self.speech_threshold
        is_silence = rms <= self.silence_threshold
        barge_in = False
        finalized = False
        truncated = False
        payload = b""

        if not agent_speaking:
            self._barge_in_latched = False

        if is_speech:
            self._speech_run += 1
            if (
                agent_speaking
                and self._speech_run >= self.speech_frames_to_trigger
                and not self._barge_in_latched
            ):
                barge_in = True
                self._barge_in_latched = True
            self._silence_ms = 0.0
            self._in_utterance = True
            self._buffer.extend(pcm_bytes)
            self._utterance_ms += duration_ms
        elif is_silence:
            self._speech_run = 0
            if self._in_utterance:
                self._silence_ms += duration_ms
                self._buffer.extend(pcm_bytes)
                self._utterance_ms += duration_ms
        else:
            self._speech_run = 0
            if self._in_utterance:
                self._silence_ms = 0.0
                self._buffer.extend(pcm_bytes)
                self._utterance_ms += duration_ms

        if self._in_utterance:
            silence_done = self._silence_ms >= self.silence_ms_to_finalize
            length_done = self._utterance_ms >= self.max_utterance_ms
            if silence_done or length_done:
                finalized = True
                truncated = length_done and not silence_done
                payload = bytes(self._buffer)
                self._in_utterance = False
                self._silence_ms = 0.0
                self._utterance_ms = 0.0
                self._buffer.clear()

        return VadDecision(
            rms=round(rms, 2),
            is_speech=is_speech,
            is_silence=is_silence,
            barge_in=barge_in,
            speech_finalized=finalized,
            truncated=truncated,
            buffered_pcm=payload,
        )
