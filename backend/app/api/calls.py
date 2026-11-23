"""Call session bootstrap endpoints for outbound verification and inbound rescue."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from sqlalchemy import select

logger = logging.getLogger(__name__)

from app.api.deps import DbDep, TenantDep, build_ws_url
from app.config import get_settings
from app.db.models import (
    CallDirection,
    CallSession,
    CallStatus,
    Order,
    OrderStatus,
    Tenant,
    utcnow,
)
from app.db.session import append_transcript
from app.schemas import (
    CallDeclineResponse,
    CallSessionSummaryOut,
    CallTimeoutResponse,
    CallTriggerResponse,
    InboundStartRequest,
    OrderOut,
    RetryDispatchResponse,
)
from app.security import hash_api_key, normalize_phone

router = APIRouter(prefix="/calls", tags=["calls"])


def _trigger_payload(
    request: Request,
    session: CallSession,
    order: Order,
    store_name: str | None = None,
) -> CallTriggerResponse:
    return CallTriggerResponse(
        session_id=session.id,
        ws_url=build_ws_url(request, session.id),
        direction=session.direction,
        status=session.status,
        order=OrderOut.from_order(order),
        store_name=store_name,
        channel=getattr(session, "channel", "VOICE"),
        provider_reference_id=getattr(session, "provider_call_sid", None) or getattr(order, "provider_reference_id", None),
    )


@router.post(
    "/trigger-outbound/{order_id}",
    response_model=CallTriggerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_outbound_call(
    order_id: str,
    request: Request,
    db: DbDep,
    tenant: TenantDep,
    channel: str | None = Query(default=None),
) -> CallTriggerResponse:
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.tenant_id == tenant.id)
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="order not found"
        )

    # If specifically requesting WhatsApp or tenant is configured strictly for WhatsApp only
    active_channel = channel.upper() if channel else None
    if active_channel == "WHATSAPP" or (active_channel is None and tenant.channel_choice == "WHATSAPP"):
        from app.services.whatsapp_agent import initiate_whatsapp_verification
        res = await initiate_whatsapp_verification(order_id=order.id, tenant_id=tenant.id)
        session = await db.scalar(select(CallSession).where(CallSession.id == res["session_id"]))
        await db.refresh(order)
        return _trigger_payload(request, session, order, store_name=tenant.name)

    # Otherwise Voice verification (Twilio Voice or Softphone)
    existing = await db.scalar(
        select(CallSession)
        .where(
            CallSession.tenant_id == tenant.id,
            CallSession.order_id == order.id,
            CallSession.direction == CallDirection.OUTBOUND_VERIFY,
            CallSession.channel == "VOICE",
            CallSession.status == CallStatus.ACTIVE,
        )
        .order_by(CallSession.created_at.desc())
        .limit(1)
    )
    if existing is not None:
        return _trigger_payload(request, existing, order, store_name=tenant.name)

    session = CallSession(
        tenant_id=tenant.id,
        order_id=order.id,
        direction=CallDirection.OUTBOUND_VERIFY,
        channel="VOICE",
        status=CallStatus.ACTIVE,
        transcript=[],
        tool_traces=[],
    )
    db.add(session)
    if order.status in (OrderStatus.PENDING_CALL, OrderStatus.PENDING_RETRY):
        order.status = OrderStatus.CALLING
    order.verification_channel = "VOICE"
    await db.commit()
    await db.refresh(session)
    await db.refresh(order)

    # If tenant has Twilio configured, place Twilio call
    if tenant.twilio_account_sid:
        from app.services.omnichannel import dispatch_twilio_voice_call
        try:
            await dispatch_twilio_voice_call(order=order, tenant=tenant, request=request)
            await db.refresh(session)
            await db.refresh(order)
        except Exception as tw_err:
            logger.warning("Twilio voice outbound trigger note: %s", tw_err)

    return _trigger_payload(request, session, order, store_name=tenant.name)


@router.post(
    "/dispatch-verification/{order_id}",
    response_model=CallTriggerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def dispatch_verification_channel(
    order_id: str,
    request: Request,
    db: DbDep,
    tenant: TenantDep,
    channel: str | None = Query(default=None),
) -> CallTriggerResponse:
    """Omnichannel dispatch: dynamically routes between Twilio Voice and WhatsApp Chat Agent."""
    from app.services.omnichannel import dispatch_order_verification
    res = await dispatch_order_verification(
        order_id=order_id,
        tenant_id=tenant.id,
        request=request,
        preferred_channel=channel.upper() if channel else None,
    )
    session = await db.scalar(select(CallSession).where(CallSession.id == res["session_id"]))
    order = await db.scalar(select(Order).where(Order.id == order_id))
    return _trigger_payload(request, session, order, store_name=tenant.name)


@router.get("/sessions", response_model=list[CallSessionSummaryOut])
async def list_call_sessions(
    db: DbDep,
    tenant: TenantDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[CallSessionSummaryOut]:
    rows = (
        await db.execute(
            select(CallSession, Order)
            .join(Order, Order.id == CallSession.order_id)
            .where(CallSession.tenant_id == tenant.id)
            .order_by(CallSession.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        CallSessionSummaryOut(
            id=session.id,
            order_id=session.order_id,
            external_order_id=order.external_order_id,
            customer_name=order.customer_name,
            direction=session.direction,
            status=session.status,
            avg_turn_latency_ms=session.avg_turn_latency_ms,
            turn_count=sum(
                1
                for entry in session.transcript
                if entry.get("role") in {"user", "assistant"}
            ),
            created_at=session.created_at,
        )
        for session, order in rows
    ]


@router.get("/pending-outbound", response_model=list[CallTriggerResponse])
async def list_pending_outbound_calls(
    request: Request,
    db: DbDep,
    x_tenant_api_key: Annotated[str | None, Header(alias="X-Tenant-API-Key")] = None,
    phone: Annotated[str | None, Query()] = None,
) -> list[CallTriggerResponse]:
    settings = get_settings()
    tenant: Tenant | None = None
    if x_tenant_api_key:
        tenant = await db.scalar(
            select(Tenant).where(Tenant.api_key_hash == hash_api_key(x_tenant_api_key))
        )
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid tenant API key",
            )
    elif not settings.allow_anonymous_tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Tenant-API-Key header is required",
        )

    query = (
        select(CallSession)
        .where(
            CallSession.direction == CallDirection.OUTBOUND_VERIFY,
            CallSession.status == CallStatus.ACTIVE,
        )
        .order_by(CallSession.created_at.desc())
        .limit(20)
    )
    if tenant is not None:
        query = query.where(CallSession.tenant_id == tenant.id)

    sessions = (await db.scalars(query)).all()
    pending = [session for session in sessions if not session.transcript]
    if not pending:
        return []

    seen_order_ids: set[str] = set()
    deduped_pending: list[CallSession] = []
    for session in pending:
        if session.order_id not in seen_order_ids:
            seen_order_ids.add(session.order_id)
            deduped_pending.append(session)
    pending = deduped_pending

    order_ids = {session.order_id for session in pending}
    order_query = select(Order).where(Order.id.in_(order_ids))
    if phone:
        order_query = order_query.where(Order.customer_phone == normalize_phone(phone))

    orders = {
        order.id: order
        for order in (await db.scalars(order_query)).all()
    }

    # Fetch store names for display on the handset
    tenant_ids = {session.tenant_id for session in pending if session.order_id in orders}
    tenants = {
        t.id: t.name
        for t in (
            await db.scalars(select(Tenant).where(Tenant.id.in_(tenant_ids)))
        ).all()
    }

    return [
        _trigger_payload(
            request,
            session,
            orders[session.order_id],
            store_name=tenants.get(session.tenant_id),
        )
        for session in pending
        if session.order_id in orders
    ]


@router.post("/{session_id}/decline", response_model=CallDeclineResponse)
async def decline_call(
    session_id: str,
    db: DbDep,
    x_tenant_api_key: Annotated[str | None, Header(alias="X-Tenant-API-Key")] = None,
) -> CallDeclineResponse:
    settings = get_settings()
    tenant: Tenant | None = None
    if x_tenant_api_key:
        tenant = await db.scalar(
            select(Tenant).where(Tenant.api_key_hash == hash_api_key(x_tenant_api_key))
        )
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid tenant API key",
            )
    elif not settings.allow_anonymous_tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Tenant-API-Key header is required",
        )

    query = select(CallSession).where(CallSession.id == session_id)
    if tenant is not None:
        query = query.where(CallSession.tenant_id == tenant.id)

    session = await db.scalar(query)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="call session not found"
        )
    if session.status == CallStatus.ACTIVE:
        session.status = CallStatus.COMPLETED
        order = await db.scalar(
            select(Order).where(
                Order.id == session.order_id,
                Order.tenant_id == session.tenant_id,
            )
        )
        if order is not None and order.status == OrderStatus.CALLING:
            order.status = OrderStatus.PENDING_CALL
        await db.commit()
    return CallDeclineResponse(session_id=session.id, status=session.status)


@router.post(
    "/start-inbound",
    response_model=CallTriggerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_inbound_call(
    payload: InboundStartRequest,
    request: Request,
    db: DbDep,
    x_tenant_api_key: Annotated[str | None, Header(alias="X-Tenant-API-Key")] = None,
) -> CallTriggerResponse:
    settings = get_settings()
    tenant: Tenant | None = None
    if x_tenant_api_key:
        tenant = await db.scalar(
            select(Tenant).where(Tenant.api_key_hash == hash_api_key(x_tenant_api_key))
        )
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid tenant API key",
            )
    elif not settings.allow_anonymous_tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Tenant-API-Key header is required",
        )

    order: Order | None = None
    if payload.order_id is not None:
        query = select(Order).where(Order.id == payload.order_id)
        if tenant is not None:
            query = query.where(Order.tenant_id == tenant.id)
        order = await db.scalar(query)
    elif payload.caller_phone is not None:
        query = select(Order).where(Order.customer_phone == payload.caller_phone)
        if tenant is not None:
            query = query.where(Order.tenant_id == tenant.id)
        order = await db.scalar(query.order_by(Order.created_at.desc()).limit(1))

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no order found for this caller; provide order_id or a known phone number",
        )

    session = CallSession(
        tenant_id=order.tenant_id,
        order_id=order.id,
        direction=CallDirection.INBOUND_RESCUE,
        status=CallStatus.ACTIVE,
        transcript=[
            {
                "role": "system",
                "text": f"inbound caller role: {payload.caller_role}",
                "timestamp_ms": 0,
            }
        ],
        tool_traces=[],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    tenant_obj = await db.scalar(select(Tenant).where(Tenant.id == order.tenant_id))
    store_name = tenant_obj.name if tenant_obj else None

    return _trigger_payload(request, session, order, store_name=store_name)


@router.post("/{session_id}/timeout", response_model=CallTimeoutResponse)
async def timeout_call(
    session_id: str,
    db: DbDep,
    x_tenant_api_key: Annotated[str | None, Header(alias="X-Tenant-API-Key")] = None,
) -> CallTimeoutResponse:
    settings = get_settings()
    tenant: Tenant | None = None
    if x_tenant_api_key:
        tenant = await db.scalar(
            select(Tenant).where(Tenant.api_key_hash == hash_api_key(x_tenant_api_key))
        )
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid tenant API key",
            )
    elif not settings.allow_anonymous_tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Tenant-API-Key header is required",
        )

    query = select(CallSession).where(CallSession.id == session_id)
    if tenant is not None:
        query = query.where(CallSession.tenant_id == tenant.id)

    session = await db.scalar(query)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="call session not found"
        )

    order = await db.scalar(
        select(Order).where(
            Order.id == session.order_id,
            Order.tenant_id == session.tenant_id,
        )
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="order not found"
        )

    if session.status == CallStatus.ACTIVE:
        session.status = CallStatus.COMPLETED
        append_transcript(
            session,
            "system",
            "Call timed out: customer did not answer within ringing duration window.",
        )

    order.call_attempts = (order.call_attempts or 0) + 1
    order.last_call_at = utcnow()
    if order.call_attempts < (order.max_call_attempts or 3):
        # Schedule next automated retry in 2 hours
        order.next_retry_at = utcnow() + timedelta(hours=2)
        order.status = OrderStatus.PENDING_RETRY
    else:
        order.status = OrderStatus.FAILED_CONTACT
        order.next_retry_at = None

    await db.commit()
    await db.refresh(order)
    return CallTimeoutResponse(
        session_id=session.id,
        status=session.status,
        order_id=order.id,
        order_status=order.status,
        call_attempts=order.call_attempts,
        max_call_attempts=order.max_call_attempts,
        next_retry_at=order.next_retry_at,
    )


@router.post("/retry-order/{order_id}", response_model=CallTriggerResponse, status_code=status.HTTP_201_CREATED)
async def retry_order_call(
    order_id: str,
    request: Request,
    db: DbDep,
    x_tenant_api_key: Annotated[str | None, Header(alias="X-Tenant-API-Key")] = None,
) -> CallTriggerResponse:
    settings = get_settings()
    tenant: Tenant | None = None
    if x_tenant_api_key:
        tenant = await db.scalar(
            select(Tenant).where(Tenant.api_key_hash == hash_api_key(x_tenant_api_key))
        )
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid tenant API key",
            )
    elif not settings.allow_anonymous_tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Tenant-API-Key header is required",
        )

    query = select(Order).where(Order.id == order_id)
    if tenant is not None:
        query = query.where(Order.tenant_id == tenant.id)
    order = await db.scalar(query)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="order not found"
        )

    # Complete any older active sessions for this order
    older_sessions = (
        await db.scalars(
            select(CallSession).where(
                CallSession.order_id == order.id,
                CallSession.status == CallStatus.ACTIVE,
            )
        )
    ).all()
    for s in older_sessions:
        s.status = CallStatus.COMPLETED

    order.status = OrderStatus.CALLING
    session = CallSession(
        tenant_id=order.tenant_id,
        order_id=order.id,
        direction=CallDirection.OUTBOUND_VERIFY,
        status=CallStatus.ACTIVE,
        transcript=[
            {
                "role": "system",
                "text": f"Outbound verification retry triggered (attempt {(order.call_attempts or 0) + 1} of {order.max_call_attempts or 3}).",
                "timestamp_ms": 0,
            }
        ],
        tool_traces=[],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    await db.refresh(order)

    tenant_obj = await db.scalar(select(Tenant).where(Tenant.id == order.tenant_id))
    store_name = tenant_obj.name if tenant_obj else None
    return _trigger_payload(request, session, order, store_name=store_name)


@router.post("/dispatch-retries", response_model=RetryDispatchResponse)
async def dispatch_due_retries(
    db: DbDep,
    x_tenant_api_key: Annotated[str | None, Header(alias="X-Tenant-API-Key")] = None,
    force: Annotated[bool, Query()] = True,
) -> RetryDispatchResponse:
    settings = get_settings()
    tenant: Tenant | None = None
    if x_tenant_api_key:
        tenant = await db.scalar(
            select(Tenant).where(Tenant.api_key_hash == hash_api_key(x_tenant_api_key))
        )
    elif not settings.allow_anonymous_tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Tenant-API-Key header is required",
        )

    now = utcnow()
    query = select(Order).where(Order.status == OrderStatus.PENDING_RETRY)
    if tenant is not None:
        query = query.where(Order.tenant_id == tenant.id)
    if not force:
        query = query.where(Order.next_retry_at <= now)

    due_orders = (await db.scalars(query.order_by(Order.created_at.asc()).limit(20))).all()
    retried_ids: list[str] = []
    for order in due_orders:
        order.status = OrderStatus.CALLING
        session = CallSession(
            tenant_id=order.tenant_id,
            order_id=order.id,
            direction=CallDirection.OUTBOUND_VERIFY,
            status=CallStatus.ACTIVE,
            transcript=[
                {
                    "role": "system",
                    "text": f"Scheduled retry dispatch (attempt {(order.call_attempts or 0) + 1} of {order.max_call_attempts or 3}).",
                    "timestamp_ms": 0,
                }
            ],
            tool_traces=[],
        )
        db.add(session)
        retried_ids.append(order.external_order_id)

    if due_orders:
        await db.commit()

    return RetryDispatchResponse(
        dispatched_count=len(retried_ids),
        orders_retried=retried_ids,
    )
