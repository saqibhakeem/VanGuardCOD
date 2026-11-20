"""Phase 4 verification: /ws/call telephony bridge and full turn execution."""

from __future__ import annotations

import asyncio
import base64
import struct
import time
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.db.models import CallSession, CallStatus, Order, OrderStatus
from app.db.session import get_session_factory
from app.main import app
from tests.conftest import TENANT_HEADERS, create_call_session


def pcm_frame(amplitude: int, frames: int = 320) -> bytes:
    return struct.pack(f"<{frames}h", *([amplitude] * frames))


def audio_chunk(amplitude: int) -> dict[str, str]:
    return {
        "event": "audio_chunk",
        "pcm16_base64": base64.b64encode(pcm_frame(amplitude)).decode("ascii"),
    }


def receive_until(
    websocket: Any,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    limit: int = 250,
) -> dict[str, Any]:
    for _ in range(limit):
        message = websocket.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected websocket frame was not received")


def end_call(websocket: Any) -> None:
    websocket.send_json({"event": "hangup"})
    receive_until(websocket, lambda frame: frame["event"] == "call_ended")


async def read_call_state(session_id: str) -> Any:
    async with get_session_factory()() as fresh:
        return (
            await fresh.execute(
                select(CallSession.status, CallSession.transcript).where(
                    CallSession.id == session_id
                )
            )
        ).first()


async def wait_for_state(
    session_id: str,
    predicate: Callable[[Any], bool],
    *,
    timeout: float = 3.0,
) -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = await read_call_state(session_id)
        if last is not None and predicate(last):
            return last
        await asyncio.sleep(0.02)
    raise AssertionError(f"call state did not settle, last: {last}")


async def test_outbound_websocket_runs_a_full_text_turn(
    db, tenant, seeded_order
):
    call_session = await create_call_session(db, tenant, seeded_order)
    session_id = call_session.id
    await db.rollback()
    client = TestClient(app)
    try:
        with client.websocket_connect(
            f"/ws/call/{session_id}", headers=TENANT_HEADERS
        ) as websocket:
            ready = websocket.receive_json()
            assert ready["event"] == "session_ready"
            assert ready["session_id"] == session_id
            assert ready["direction"] == "OUTBOUND_VERIFY"
            assert ready["order"]["external_order_id"] == "ORD-9042"

            greeting = receive_until(
                websocket,
                lambda frame: frame["event"] == "transcript_update"
                and frame["role"] == "assistant",
            )
            assert "Ayesha" in greeting["text"]
            assert "ORD-9042" in greeting["text"]

            websocket.send_json(
                {
                    "event": "text_utterance",
                    "text": "Yes, please confirm the order and deliver tomorrow evening.",
                }
            )

            user_turn = receive_until(
                websocket,
                lambda frame: frame["event"] == "transcript_update"
                and frame["role"] == "user",
            )
            assert "confirm the order" in user_turn["text"]

            tool_event = receive_until(
                websocket, lambda frame: frame["event"] == "tool_trace"
            )
            assert tool_event["tool_name"] == "confirm_cod_order"
            assert tool_event["status"] == "SUCCESS"

            telemetry = receive_until(
                websocket,
                lambda frame: frame["event"] == "telemetry"
                and frame["llm_ms"] > 0,
            )
            assert telemetry["stt_ms"] == 0
            assert telemetry["llm_ms"] > 0
            assert telemetry["tts_ms"] >= 0
            assert telemetry["total_ms"] == pytest.approx(
                telemetry["stt_ms"] + telemetry["llm_ms"] + telemetry["tts_ms"],
                abs=0.05,
            )

            websocket.send_json({"event": "hangup"})
            ended = receive_until(
                websocket, lambda frame: frame["event"] == "call_ended"
            )
            assert ended["reason"] == "hangup"
    finally:
        client.close()

    await db.refresh(seeded_order)
    await db.refresh(call_session)
    assert seeded_order.status == OrderStatus.VERIFIED
    assert seeded_order.verified_landmark is not None
    assert call_session.status == CallStatus.COMPLETED
    assert call_session.avg_turn_latency_ms > 0
    assert any(entry["role"] == "user" for entry in call_session.transcript)
    assert any(
        trace["tool_name"] == "confirm_cod_order" and trace["status"] == "SUCCESS"
        for trace in call_session.tool_traces
    )


async def test_websocket_streams_tts_audio_chunks(db, tenant, seeded_order):
    call_session = await create_call_session(db, tenant, seeded_order)
    session_id = call_session.id
    await db.rollback()
    client = TestClient(app)
    try:
        with client.websocket_connect(
            f"/ws/call/{session_id}", headers=TENANT_HEADERS
        ) as websocket:
            assert websocket.receive_json()["event"] == "session_ready"
            audio = receive_until(
                websocket, lambda frame: frame["event"] == "tts_audio"
            )
            payload = base64.b64decode(audio["wav_base64"])
            assert payload[:4] == b"RIFF"
            assert payload[8:12] == b"WAVE"
            assert isinstance(audio["sentence_index"], int)
            assert audio["text"]
            end_call(websocket)
    finally:
        client.close()


async def test_websocket_audio_chunk_path_transcribes_and_runs_tool(
    db, tenant, seeded_order
):
    call_session = await create_call_session(db, tenant, seeded_order)
    session_id = call_session.id
    await db.rollback()
    client = TestClient(app)
    try:
        with client.websocket_connect(
            f"/ws/call/{session_id}", headers=TENANT_HEADERS
        ) as websocket:
            assert websocket.receive_json()["event"] == "session_ready"

            for _ in range(4):
                websocket.send_json(audio_chunk(7000))
            for _ in range(23):
                websocket.send_json(audio_chunk(0))

            stt_result = receive_until(
                websocket, lambda frame: frame["event"] == "stt_result"
            )
            assert "confirm" in stt_result["text"].lower()
            assert stt_result["latency_ms"] >= 0

            tool_event = receive_until(
                websocket, lambda frame: frame["event"] == "tool_trace"
            )
            assert tool_event["tool_name"] == "confirm_cod_order"
            assert tool_event["status"] == "SUCCESS"

            receive_until(
                websocket,
                lambda frame: frame["event"] == "telemetry"
                and frame["llm_ms"] > 0,
            )
            end_call(websocket)
    finally:
        client.close()

    await db.refresh(seeded_order)
    assert seeded_order.status == OrderStatus.VERIFIED


async def test_websocket_barge_in_clears_playback(db, tenant, seeded_order):
    call_session = await create_call_session(db, tenant, seeded_order)
    session_id = call_session.id
    await db.rollback()
    client = TestClient(app)
    try:
        with client.websocket_connect(
            f"/ws/call/{session_id}", headers=TENANT_HEADERS
        ) as websocket:
            assert websocket.receive_json()["event"] == "session_ready"
            websocket.send_json({"event": "barge_in"})
            cleared = receive_until(
                websocket, lambda frame: frame["event"] == "clear_audio"
            )
            assert cleared["event"] == "clear_audio"
            end_call(websocket)
    finally:
        client.close()


async def test_inbound_websocket_greets_caller(db, tenant, seeded_order):
    call_session = await create_call_session(
        db, tenant, seeded_order, direction="INBOUND_RESCUE"
    )
    session_id = call_session.id
    await db.rollback()
    client = TestClient(app)
    try:
        with client.websocket_connect(
            f"/ws/call/{session_id}", headers=TENANT_HEADERS
        ) as websocket:
            ready = websocket.receive_json()
            assert ready["direction"] == "INBOUND_RESCUE"
            greeting = receive_until(
                websocket,
                lambda frame: frame["event"] == "transcript_update"
                and frame["role"] == "assistant",
            )
            assert "customer or the delivery rider" in greeting["text"]
            end_call(websocket)
    finally:
        client.close()


async def test_websocket_handles_ping_and_invalid_json(db, tenant, seeded_order):
    call_session = await create_call_session(db, tenant, seeded_order)
    session_id = call_session.id
    await db.rollback()
    client = TestClient(app)
    try:
        with client.websocket_connect(
            f"/ws/call/{session_id}", headers=TENANT_HEADERS
        ) as websocket:
            assert websocket.receive_json()["event"] == "session_ready"

            websocket.send_text("this is not json")
            invalid = receive_until(
                websocket, lambda frame: frame["event"] == "error"
            )
            assert invalid["code"] == "invalid_json"

            websocket.send_json({"event": "ping"})
            pong = receive_until(websocket, lambda frame: frame["event"] == "pong")
            assert pong["event"] == "pong"

            websocket.send_json({"event": "unsupported"})
            unknown = receive_until(
                websocket,
                lambda frame: frame["event"] == "error"
                and frame["code"] == "unknown_event",
            )
            assert unknown["event_name"] == "unsupported"
            end_call(websocket)
    finally:
        client.close()


async def test_websocket_rejects_bad_tenant_key(db, tenant, seeded_order):
    call_session = await create_call_session(db, tenant, seeded_order)
    session_id = call_session.id
    await db.rollback()
    client = TestClient(app)
    try:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(
                f"/ws/call/{session_id}",
                headers={"X-Tenant-API-Key": "not-a-real-key"},
            ) as websocket:
                websocket.receive_json()
        assert excinfo.value.code == 4401
    finally:
        client.close()


async def test_websocket_rejects_unknown_session(db, tenant, seeded_order):
    client = TestClient(app)
    try:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(
                "/ws/call/00000000-0000-0000-0000-000000000000",
                headers=TENANT_HEADERS,
            ) as websocket:
                websocket.receive_json()
        assert excinfo.value.code == 4404
    finally:
        client.close()


async def test_websocket_rejects_completed_session(db, tenant, seeded_order):
    call_session = await create_call_session(db, tenant, seeded_order)
    call_session.status = CallStatus.COMPLETED
    await db.commit()
    session_id = call_session.id
    await db.rollback()
    client = TestClient(app)
    try:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(
                f"/ws/call/{session_id}", headers=TENANT_HEADERS
            ) as websocket:
                websocket.receive_json()
        assert excinfo.value.code == 4409
    finally:
        client.close()


async def test_disconnect_keeps_call_resumable(db, tenant, seeded_order):
    call_session = await create_call_session(db, tenant, seeded_order)
    session_id = call_session.id
    await db.rollback()
    client = TestClient(app)
    try:
        with client.websocket_connect(
            f"/ws/call/{session_id}", headers=TENANT_HEADERS
        ) as websocket:
            assert websocket.receive_json()["event"] == "session_ready"
            receive_until(
                websocket,
                lambda frame: frame["event"] == "transcript_update"
                and frame["role"] == "assistant",
            )
            websocket.send_json({"event": "ping"})
            receive_until(websocket, lambda frame: frame["event"] == "pong")
    finally:
        client.close()

    status, transcript = await wait_for_state(
        session_id,
        lambda state: any(
            entry.get("role") == "assistant" for entry in state[1] or []
        ),
    )
    assert status == CallStatus.ACTIVE
    assert transcript


async def test_reconnect_resumes_without_replaying_greeting(db, tenant, seeded_order):
    call_session = await create_call_session(db, tenant, seeded_order)
    session_id = call_session.id
    await db.rollback()
    client = TestClient(app)
    try:
        with client.websocket_connect(
            f"/ws/call/{session_id}", headers=TENANT_HEADERS
        ) as websocket:
            ready = websocket.receive_json()
            assert ready["event"] == "session_ready"
            assert ready["resumed"] is False
            receive_until(
                websocket,
                lambda frame: frame["event"] == "transcript_update"
                and frame["role"] == "assistant",
            )
            websocket.send_json({"event": "ping"})
            receive_until(websocket, lambda frame: frame["event"] == "pong")

        await wait_for_state(
            session_id,
            lambda state: any(
                entry.get("role") == "assistant" for entry in state[1] or []
            ),
        )

        with client.websocket_connect(
            f"/ws/call/{session_id}", headers=TENANT_HEADERS
        ) as websocket:
            ready = websocket.receive_json()
            assert ready["event"] == "session_ready"
            assert ready["resumed"] is True

            websocket.send_json({"event": "ping"})
            assert websocket.receive_json()["event"] == "pong"
            end_call(websocket)
    finally:
        client.close()
