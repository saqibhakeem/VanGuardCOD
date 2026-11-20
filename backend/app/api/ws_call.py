"""WebSocket telephony bridge for browser PCM16 softphone sessions."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket
from sqlalchemy import select

from app.agents.inbound_rescue import build_inbound_agent
from app.agents.outbound_verifier import build_outbound_agent
from app.config import get_settings
from app.db.models import CallDirection, CallSession, CallStatus, Order, Tenant
from app.db.session import get_session_factory
from app.security import hash_api_key
from app.voice.session import CLOSED_HANGUP, AudioSessionController

router = APIRouter(tags=["telephony"])

SUPPORTED_CALLER_ROLES = {"customer", "rider"}
TERMINAL_STATUSES = {CallStatus.COMPLETED, CallStatus.FAILED}

_PENDING_FINALIZERS: dict[str, asyncio.Task[None]] = {}
_ACTIVE_SESSIONS: set[str] = set()


async def cancel_pending_finalizers() -> None:
    """Cancel every scheduled grace finalizer; used by tests and app shutdown."""

    tasks = list(_PENDING_FINALIZERS.values())
    _PENDING_FINALIZERS.clear()
    _ACTIVE_SESSIONS.clear()
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def _cancel_finalizer(session_id: str) -> None:
    task = _PENDING_FINALIZERS.pop(session_id, None)
    if task is not None and not task.done():
        task.cancel()


def _schedule_finalizer(session_id: str, tenant_id: str) -> None:
    grace_seconds = get_settings().call_reconnect_grace_seconds
    _cancel_finalizer(session_id)
    task = asyncio.create_task(
        _finalize_after_grace(session_id, tenant_id, grace_seconds),
        name=f"call-finalizer-{session_id}",
    )
    _PENDING_FINALIZERS[session_id] = task


async def _finalize_after_grace(
    session_id: str, tenant_id: str, grace_seconds: float
) -> None:
    try:
        await asyncio.sleep(max(grace_seconds, 0.0))
        if session_id in _ACTIVE_SESSIONS:
            return
        async with get_session_factory()() as db:
            call_session = await db.scalar(
                select(CallSession).where(
                    CallSession.id == session_id,
                    CallSession.tenant_id == tenant_id,
                )
            )
            if (
                call_session is not None
                and call_session.status == CallStatus.ACTIVE
                and session_id not in _ACTIVE_SESSIONS
            ):
                call_session.status = CallStatus.COMPLETED
                await db.commit()
    except asyncio.CancelledError:
        raise
    finally:
        if _PENDING_FINALIZERS.get(session_id) is asyncio.current_task():
            _PENDING_FINALIZERS.pop(session_id, None)


def _build_history(call_session: CallSession) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for entry in call_session.transcript or []:
        role = str(entry.get("role") or "")
        text = str(entry.get("text") or "").strip()
        if role in {"user", "assistant"} and text:
            history.append({"role": role, "content": text})
    return history


def _inbound_caller_role(websocket: WebSocket, call_session: CallSession) -> str:
    query_role = (websocket.query_params.get("caller_role") or "").strip().lower()
    if query_role in SUPPORTED_CALLER_ROLES:
        return query_role
    for entry in call_session.transcript or []:
        text = str(entry.get("text") or "")
        if text.startswith("inbound caller role:"):
            value = text.split(":", 1)[1].strip().lower()
            if value in SUPPORTED_CALLER_ROLES:
                return value
    return "customer"


async def _resolve_tenant(websocket: WebSocket, db: Any) -> Tenant | None:
    settings = get_settings()
    api_key = websocket.headers.get("x-tenant-api-key") or websocket.query_params.get(
        "api_key"
    )
    if not api_key and settings.allow_anonymous_tenant:
        api_key = settings.default_tenant_api_key
    if not api_key:
        return None
    return await db.scalar(
        select(Tenant).where(Tenant.api_key_hash == hash_api_key(api_key))
    )


@router.websocket("/ws/call/{session_id}")
async def call_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    async with get_session_factory()() as db:
        tenant = await _resolve_tenant(websocket, db)
        if tenant is None:
            await websocket.close(code=4401, reason="invalid tenant API key")
            return

        call_session = await db.scalar(
            select(CallSession).where(
                CallSession.id == session_id,
                CallSession.tenant_id == tenant.id,
            )
        )
        if call_session is None:
            await websocket.close(code=4404, reason="call session not found")
            return
        if call_session.status in TERMINAL_STATUSES:
            await websocket.close(
                code=4409, reason=f"call session is {call_session.status}"
            )
            return
        order = await db.scalar(
            select(Order).where(
                Order.id == call_session.order_id,
                Order.tenant_id == tenant.id,
            )
        )
        if order is None:
            await websocket.close(code=4404, reason="order not found for call session")
            return

        _ACTIVE_SESSIONS.add(call_session.id)
        _cancel_finalizer(call_session.id)
        history = _build_history(call_session)
        resumed = bool(history)

        controller_ref: dict[str, AudioSessionController] = {}

        async def forward_event(event: dict[str, Any]) -> None:
            controller = controller_ref.get("controller")
            if controller is not None:
                await controller.publish(event)

        if call_session.direction == CallDirection.OUTBOUND_VERIFY:
            agent = build_outbound_agent(
                db,
                tenant,
                order,
                call_session,
                on_event=forward_event,
                history=history,
            )
        else:
            agent = build_inbound_agent(
                db,
                tenant,
                order,
                call_session,
                caller_role=_inbound_caller_role(websocket, call_session),
                on_event=forward_event,
                history=history,
            )

        controller = AudioSessionController(
            websocket=websocket,
            agent=agent,
            db=db,
            call_session=call_session,
            order=order,
            voice=tenant.voice_persona or None,
            resume=resumed,
        )
        controller_ref["controller"] = controller

        try:
            await controller.run()
        except asyncio.CancelledError:
            raise
        finally:
            _ACTIVE_SESSIONS.discard(call_session.id)
            if controller.closed_reason != CLOSED_HANGUP:
                try:
                    _schedule_finalizer(call_session.id, tenant.id)
                except RuntimeError:
                    pass
