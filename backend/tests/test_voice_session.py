"""Phase 4 hardening: controller error isolation, barge-in epochs, and turn timing."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from typing import Any, Callable

from app.db.models import CallStatus
from app.voice.session import AudioSessionController
from app.voice.tts_provider import SpeechChunk
from tests.conftest import create_call_session


class FakeWebSocket:
    """Minimal WebSocket double that records outbound frames."""

    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []
        self._incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.frames.append(payload)

    async def receive(self) -> dict[str, Any]:
        return await self._incoming.get()

    async def send(self, payload: dict[str, Any]) -> None:
        await self._incoming.put(
            {"type": "websocket.receive", "text": json.dumps(payload)}
        )


async def wait_for_frame(
    websocket: FakeWebSocket,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for frame in websocket.frames:
            if predicate(frame):
                return frame
        await asyncio.sleep(0.005)
    raise AssertionError("expected websocket frame was not emitted")


async def wait_for_turn(agent: "StubAgent", *, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if agent.turns:
            return
        await asyncio.sleep(0.005)
    raise AssertionError("agent turn did not start")


class StubAgent:
    """Agent double with an optional failure, gate, and canned reply."""

    def __init__(
        self,
        *,
        reply: str = "",
        fail: Exception | None = None,
        gate: asyncio.Event | None = None,
    ) -> None:
        self.paused = False
        self.pending_approval_ids: list[str] = []
        self.reply = reply
        self.fail = fail
        self.gate = gate
        self.started = 0
        self.turns: list[str] = []

    async def start(self) -> SimpleNamespace:
        self.started += 1
        return SimpleNamespace(text="")

    async def run_turn(self, text: str) -> SimpleNamespace:
        self.turns.append(text)
        if self.gate is not None:
            await self.gate.wait()
        if self.fail is not None:
            raise self.fail
        return SimpleNamespace(
            text=self.reply, llm_ms=1.0, paused=False, approval_ids=[]
        )


class SlowTTS:
    """TTS double that yields many chunks slowly so playback can be interrupted."""

    def __init__(self, chunks: int = 40, delay: float = 0.005) -> None:
        self.chunks = chunks
        self.delay = delay
        self.requests = 0

    async def stream_speech(self, text: str, *, voice: str | None = None):
        self.requests += 1
        for index in range(self.chunks):
            await asyncio.sleep(self.delay)
            yield SpeechChunk(
                text=f"{text} part {index}", wav_bytes=b"RIFFfake", index=index
            )


async def test_agent_failure_emits_error_and_keeps_session_open(
    db, tenant, seeded_order
):
    call_session = await create_call_session(db, tenant, seeded_order)
    websocket = FakeWebSocket()
    controller = AudioSessionController(
        websocket=websocket,
        agent=StubAgent(fail=ValueError("provider exploded")),
        db=db,
        call_session=call_session,
        order=seeded_order,
    )
    task = asyncio.create_task(controller.run())
    try:
        await wait_for_frame(websocket, lambda frame: frame["event"] == "session_ready")
        await websocket.send({"event": "text_utterance", "text": "hello"})

        error = await wait_for_frame(
            websocket,
            lambda frame: frame["event"] == "error"
            and frame.get("code") == "agent_failed",
        )
        assert "provider exploded" in error["message"]

        await websocket.send({"event": "ping"})
        await wait_for_frame(websocket, lambda frame: frame["event"] == "pong")
        assert controller.closed_reason is None
    finally:
        await websocket.send({"event": "hangup"})
        await asyncio.wait_for(task, timeout=5)

    assert call_session.status == CallStatus.COMPLETED


async def test_barge_in_during_generation_discards_pending_reply(
    db, tenant, seeded_order
):
    call_session = await create_call_session(db, tenant, seeded_order)
    websocket = FakeWebSocket()
    gate = asyncio.Event()
    agent = StubAgent(reply="This reply must never be spoken.", gate=gate)
    controller = AudioSessionController(
        websocket=websocket,
        agent=agent,
        db=db,
        call_session=call_session,
        order=seeded_order,
        tts=SlowTTS(),
    )
    task = asyncio.create_task(controller.run())
    try:
        await wait_for_frame(websocket, lambda frame: frame["event"] == "session_ready")
        await websocket.send({"event": "text_utterance", "text": "hello"})
        await wait_for_turn(agent)

        await websocket.send({"event": "barge_in"})
        await wait_for_frame(websocket, lambda frame: frame["event"] == "clear_audio")

        gate.set()
        await asyncio.sleep(0.15)
        assert not any(frame["event"] == "tts_audio" for frame in websocket.frames)
    finally:
        await websocket.send({"event": "hangup"})
        await asyncio.wait_for(task, timeout=5)

    assert call_session.status == CallStatus.COMPLETED


async def test_barge_in_stops_slow_tts_stream(db, tenant, seeded_order):
    call_session = await create_call_session(db, tenant, seeded_order)
    websocket = FakeWebSocket()
    controller = AudioSessionController(
        websocket=websocket,
        agent=StubAgent(reply="A deliberately long spoken answer."),
        db=db,
        call_session=call_session,
        order=seeded_order,
        tts=SlowTTS(chunks=100, delay=0.01),
    )
    task = asyncio.create_task(controller.run())
    try:
        await wait_for_frame(websocket, lambda frame: frame["event"] == "session_ready")
        await websocket.send({"event": "text_utterance", "text": "hello"})
        await wait_for_frame(websocket, lambda frame: frame["event"] == "tts_audio")

        await websocket.send({"event": "barge_in"})
        cleared = await wait_for_frame(
            websocket, lambda frame: frame["event"] == "clear_audio"
        )
        position = websocket.frames.index(cleared)
        await asyncio.sleep(0.15)

        assert all(
            frame["event"] != "tts_audio" for frame in websocket.frames[position + 1 :]
        )
        assert controller.is_agent_speaking is False
    finally:
        await websocket.send({"event": "hangup"})
        await asyncio.wait_for(task, timeout=5)

    assert call_session.status == CallStatus.COMPLETED


async def test_text_turn_does_not_block_the_receive_loop(db, tenant, seeded_order):
    call_session = await create_call_session(db, tenant, seeded_order)
    websocket = FakeWebSocket()
    gate = asyncio.Event()
    controller = AudioSessionController(
        websocket=websocket,
        agent=StubAgent(reply="", gate=gate),
        db=db,
        call_session=call_session,
        order=seeded_order,
        tts=SlowTTS(),
    )
    task = asyncio.create_task(controller.run())
    try:
        await wait_for_frame(websocket, lambda frame: frame["event"] == "session_ready")
        await websocket.send({"event": "text_utterance", "text": "first"})
        await wait_for_turn(controller.agent)

        await websocket.send({"event": "ping"})
        await wait_for_frame(websocket, lambda frame: frame["event"] == "pong")
        assert len(controller.agent.turns) == 1

        gate.set()
        await asyncio.sleep(0.05)
    finally:
        await websocket.send({"event": "hangup"})
        await asyncio.wait_for(task, timeout=5)

    assert call_session.status == CallStatus.COMPLETED
