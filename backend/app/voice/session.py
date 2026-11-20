"""Dual-mode audio session controller bridging WebSockets, VAD, STT, agents, and TTS."""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runtime import AutonomousVoiceAgent
from app.db.models import CallSession, CallStatus, Order
from app.db.session import append_transcript
from app.schemas import OrderOut
from app.voice.audio import DEFAULT_SAMPLE_RATE
from app.voice.stt_groq import GroqSpeechToText, SpeechToText
from app.voice.tts_provider import GroqTextToSpeech, TextToSpeech
from app.voice.vad import RmsBargeInDetector

logger = logging.getLogger(__name__)

CLOSED_HANGUP = "hangup"
CLOSED_DISCONNECT = "disconnect"
CLOSED_ERROR = "error"


@dataclass(slots=True)
class SpeechRequest:
    text: str
    stt_ms: float = 0.0
    llm_ms: float = 0.0
    turn_started: float = field(default_factory=time.perf_counter)
    is_turn: bool = False


class AudioSessionController:
    """Single-writer WebSocket session with concurrent receive, turn, and speaker tasks."""

    def __init__(
        self,
        *,
        websocket: WebSocket,
        agent: AutonomousVoiceAgent,
        db: AsyncSession,
        call_session: CallSession,
        order: Order,
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
        vad: RmsBargeInDetector | None = None,
        voice: str | None = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        resume: bool = False,
    ) -> None:
        self.websocket = websocket
        self.agent = agent
        self.db = db
        self.call_session = call_session
        self.session_id = call_session.id
        self.order = order
        self.stt = stt or GroqSpeechToText(sample_rate=sample_rate)
        self.tts = tts or GroqTextToSpeech(voice=voice)
        self.vad = vad or RmsBargeInDetector(sample_rate=sample_rate)
        self.voice = voice
        self.sample_rate = sample_rate
        self.resume = resume

        self._outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._speech: asyncio.Queue[SpeechRequest] = asyncio.Queue()
        self._interrupt = asyncio.Event()
        self._speaker_lock = asyncio.Lock()
        self._db_lock = asyncio.Lock()
        self._sender_task: asyncio.Task[None] | None = None
        self._speaker_task: asyncio.Task[None] | None = None
        self._turn_task: asyncio.Task[None] | None = None
        self._turn_tasks: set[asyncio.Task[None]] = set()
        self._aux_tasks: set[asyncio.Task[Any]] = set()
        self._is_agent_speaking = False
        self._running = False
        self._turn_index = 0
        self._latency_samples = 0
        self._interrupt_epoch = 0
        self._closed_reason: str | None = None
        self._last_error: str | None = None

    @property
    def is_agent_speaking(self) -> bool:
        return self._is_agent_speaking

    @property
    def closed_reason(self) -> str | None:
        return self._closed_reason

    @property
    def last_error(self) -> str | None:
        return self._last_error

    async def publish(self, event: dict[str, Any]) -> None:
        await self._outbound.put(event)

    async def run(self) -> None:
        await self.publish(
            {
                "event": "session_ready",
                "session_id": self.session_id,
                "direction": self.call_session.direction,
                "resumed": self.resume,
                "order": OrderOut.from_order(self.order).model_dump(mode="json"),
            }
        )
        self._sender_task = asyncio.create_task(self._sender_loop(), name="ws-sender")
        self._speaker_task = asyncio.create_task(self._speaker_loop(), name="ws-speaker")
        self._running = True
        try:
            if not self.resume:
                greeting = await self.agent.start()
                if greeting.text:
                    async with self._db_lock:
                        append_transcript(self.call_session, "assistant", greeting.text)
                        await self.db.commit()
                    await self._speech.put(SpeechRequest(text=greeting.text))
            await self._receive_loop()
        except WebSocketDisconnect:
            self._closed_reason = self._closed_reason or CLOSED_DISCONNECT
        except asyncio.CancelledError:
            self._closed_reason = self._closed_reason or CLOSED_DISCONNECT
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("audio session failed for %s", self.session_id)
            self._closed_reason = CLOSED_ERROR
            self._last_error = f"{type(exc).__name__}: {exc}"
            await self.publish(
                {
                    "event": "error",
                    "code": "session_failed",
                    "message": self._last_error,
                }
            )
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._outbound.join(), timeout=1.0)
        finally:
            await self._shutdown()

    async def _receive_loop(self) -> None:
        while True:
            message = await self.websocket.receive()
            if message.get("type") == "websocket.disconnect":
                self._closed_reason = self._closed_reason or CLOSED_DISCONNECT
                return
            raw = message.get("text")
            if raw is None:
                payload_bytes = message.get("bytes")
                if not payload_bytes:
                    continue
                raw = payload_bytes.decode("utf-8", "ignore")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await self.publish({"event": "error", "code": "invalid_json"})
                continue
            if not isinstance(payload, dict):
                await self.publish({"event": "error", "code": "invalid_frame"})
                continue

            event = str(payload.get("event") or "").strip()
            if event == "audio_chunk":
                await self._handle_audio_chunk(payload)
            elif event == "text_utterance":
                await self._handle_text_utterance(payload)
            elif event == "barge_in":
                await self._interrupt_playback()
            elif event == "hangup":
                await self._hangup()
                return
            elif event == "ping":
                await self.publish({"event": "pong"})
            else:
                await self.publish(
                    {"event": "error", "code": "unknown_event", "event_name": event}
                )

    async def _handle_text_utterance(self, payload: dict[str, Any]) -> None:
        text = str(payload.get("text") or "").strip()
        if not text:
            await self.publish({"event": "error", "code": "empty_utterance"})
            return
        self._dispatch_turn(text, stt_ms=0.0)

    async def _handle_audio_chunk(self, payload: dict[str, Any]) -> None:
        encoded = payload.get("pcm16_base64")
        if not isinstance(encoded, str) or not encoded.strip():
            await self.publish({"event": "error", "code": "missing_pcm16_base64"})
            return
        try:
            pcm_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            await self.publish({"event": "error", "code": "invalid_pcm16_base64"})
            return

        decision = self.vad.process_frame(
            pcm_bytes, agent_speaking=self._is_agent_speaking
        )
        if decision.barge_in:
            await self._interrupt_playback()
            await self.publish(
                {
                    "event": "vad_barge_in",
                    "rms": decision.rms,
                    "threshold": self.vad.speech_threshold,
                }
            )
        if not (decision.speech_finalized and decision.buffered_pcm):
            return

        try:
            transcript = await self.stt.transcribe_pcm_buffer(
                decision.buffered_pcm, sample_rate=self.sample_rate
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("speech-to-text failed for %s", self.session_id)
            await self.publish(
                {
                    "event": "error",
                    "code": "stt_failed",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
            return

        await self.publish(
            {
                "event": "stt_result",
                "text": transcript.text,
                "latency_ms": transcript.latency_ms,
                "audio_ms": transcript.audio_ms,
                "truncated": decision.truncated,
            }
        )
        if transcript.text.strip():
            self._dispatch_turn(transcript.text, stt_ms=transcript.latency_ms)

    def _dispatch_turn(self, text: str, *, stt_ms: float) -> None:
        previous = self._turn_task
        task = asyncio.create_task(
            self._turn_worker(
                text,
                stt_ms=stt_ms,
                interrupt_epoch=self._interrupt_epoch,
                previous=previous if previous is not None and not previous.done() else None,
            ),
            name="ws-turn",
        )
        self._turn_task = task
        self._turn_tasks.add(task)
        task.add_done_callback(self._turn_tasks.discard)

    async def _turn_worker(
        self,
        text: str,
        *,
        stt_ms: float,
        interrupt_epoch: int,
        previous: asyncio.Task[None] | None,
    ) -> None:
        if previous is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await previous

        async with self._db_lock:
            await self._resume_if_operator_approved()
            if self.agent.paused:
                await self.publish(
                    {
                        "event": "approval_hold",
                        "message": "This call is paused for operator review.",
                        "approval_ids": list(self.agent.pending_approval_ids),
                    }
                )
                return

            turn_started = time.perf_counter()
            try:
                append_transcript(self.call_session, "user", text)
                turn = await self.agent.run_turn(text)
                if turn.text:
                    append_transcript(self.call_session, "assistant", turn.text)
                await self.db.commit()
            except asyncio.CancelledError:
                with contextlib.suppress(Exception):
                    await self.db.rollback()
                raise
            except Exception as exc:  # noqa: BLE001
                with contextlib.suppress(Exception):
                    await self.db.rollback()
                with contextlib.suppress(Exception):
                    await self.db.refresh(self.call_session)
                with contextlib.suppress(Exception):
                    await self.db.refresh(self.order)
                logger.exception("agent turn failed for %s", self.session_id)
                await self.publish(
                    {
                        "event": "error",
                        "code": "agent_failed",
                        "message": f"{type(exc).__name__}: {exc}",
                    }
                )
                return

        if interrupt_epoch != self._interrupt_epoch:
            return
        if turn.paused:
            await self.publish(
                {
                    "event": "call_paused",
                    "approval_ids": turn.approval_ids,
                    "reason": "human approval required",
                }
            )
        if turn.text:
            await self._speech.put(
                SpeechRequest(
                    text=turn.text,
                    stt_ms=stt_ms,
                    llm_ms=turn.llm_ms,
                    turn_started=turn_started,
                    is_turn=True,
                )
            )

    async def _resume_if_operator_approved(self) -> None:
        if not self.agent.paused:
            return
        await self.db.refresh(self.call_session)
        if self.call_session.status == CallStatus.ACTIVE:
            self.agent.paused = False
            self.agent.pending_approval_ids = []
            await self.publish({"event": "approval_resolved", "action": "resumed"})

    async def _sender_loop(self) -> None:
        while True:
            payload = await self._outbound.get()
            try:
                await self.websocket.send_json(payload)
            except (WebSocketDisconnect, RuntimeError):
                self._closed_reason = self._closed_reason or CLOSED_DISCONNECT
                return
            finally:
                self._outbound.task_done()

    async def _speaker_loop(self) -> None:
        while True:
            request = await self._speech.get()
            if self._interrupt.is_set():
                continue
            self._is_agent_speaking = True
            tts_started = time.perf_counter()
            emitted = 0
            try:
                async for chunk in self.tts.stream_speech(request.text, voice=self.voice):
                    if self._interrupt.is_set():
                        break
                    await self.publish(
                        {
                            "event": "tts_audio",
                            "wav_base64": base64.b64encode(chunk.wav_bytes).decode("ascii"),
                            "sentence_index": chunk.index,
                            "text": chunk.text,
                        }
                    )
                    emitted += 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("text-to-speech failed for %s", self.session_id)
                await self.publish(
                    {
                        "event": "error",
                        "code": "tts_failed",
                        "message": f"{type(exc).__name__}: {exc}",
                    }
                )
            finally:
                self._is_agent_speaking = False

            if self._interrupt.is_set():
                continue
            if emitted == 0:
                continue
            await self._run_telemetry(request, tts_started)

    async def _run_telemetry(self, request: SpeechRequest, tts_started: float) -> None:
        task = asyncio.create_task(
            self._emit_telemetry(request, tts_started), name="ws-telemetry"
        )
        self._aux_tasks.add(task)
        task.add_done_callback(self._on_aux_done)
        await asyncio.shield(task)

    def _on_aux_done(self, task: asyncio.Task[Any]) -> None:
        self._aux_tasks.discard(task)
        if not task.cancelled():
            with contextlib.suppress(Exception):
                task.exception()

    async def _emit_telemetry(self, request: SpeechRequest, tts_started: float) -> None:
        tts_ms = round((time.perf_counter() - tts_started) * 1000, 2)
        total_ms = round(request.stt_ms + request.llm_ms + tts_ms, 2)
        await self.publish(
            {
                "event": "telemetry",
                "stt_ms": round(request.stt_ms, 2),
                "llm_ms": round(request.llm_ms, 2),
                "tts_ms": tts_ms,
                "total_ms": total_ms,
                "turn_index": self._turn_index,
            }
        )
        self._turn_index += 1
        if request.is_turn:
            async with self._db_lock:
                self._latency_samples += 1
                previous = float(self.call_session.avg_turn_latency_ms or 0.0)
                average = previous + (total_ms - previous) / self._latency_samples
                self.call_session.avg_turn_latency_ms = round(average, 2)
                await self.db.commit()

    async def _interrupt_playback(self) -> None:
        async with self._speaker_lock:
            self._interrupt.set()
            self._interrupt_epoch += 1
            await self._stop_speaker()
            self._drain_speech_queue()
            await self.publish({"event": "clear_audio"})
            await self._start_speaker()

    async def _stop_speaker(self) -> None:
        task = self._speaker_task
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _start_speaker(self) -> None:
        if not self._running:
            return
        if self._speaker_task is not None and not self._speaker_task.done():
            return
        self._interrupt = asyncio.Event()
        self._speaker_task = asyncio.create_task(self._speaker_loop(), name="ws-speaker")

    async def _stop_turn(self) -> None:
        tasks = [task for task in self._turn_tasks if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _drain_speech_queue(self) -> None:
        while True:
            try:
                self._speech.get_nowait()
            except asyncio.QueueEmpty:
                return

    async def _hangup(self) -> None:
        self._closed_reason = CLOSED_HANGUP
        await self._stop_turn()
        async with self._db_lock:
            with contextlib.suppress(Exception):
                if inspect(self.call_session).expired:
                    await self.db.refresh(self.call_session)
            self.call_session.status = CallStatus.COMPLETED
            await self.db.commit()
        await self.publish(
            {"event": "call_ended", "session_id": self.session_id, "reason": "hangup"}
        )
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._outbound.join(), timeout=2.0)

    async def _shutdown(self) -> None:
        self._running = False
        self._closed_reason = self._closed_reason or CLOSED_DISCONNECT
        self._interrupt.set()

        tasks = {
            task
            for task in (
                self._turn_task,
                self._speaker_task,
                self._sender_task,
                *self._turn_tasks,
            )
            if task is not None
        }
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if self._aux_tasks:
            pending = list(self._aux_tasks)
            _done, still_pending = await asyncio.wait(pending, timeout=2.0)
            for task in still_pending:
                task.cancel()
            if still_pending:
                await asyncio.gather(*still_pending, return_exceptions=True)

        async with self._db_lock:
            try:
                await self.db.commit()
            except Exception:  # noqa: BLE001
                with contextlib.suppress(Exception):
                    await self.db.rollback()
