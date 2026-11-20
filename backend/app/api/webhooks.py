"""Order ingestion webhook: computes RTO risk and queues an outbound call."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import DbDep, TenantDep, build_ws_url
from app.db.models import (
    CallDirection,
    CallSession,
    CallStatus,
    Order,
    OrderStatus,
)
from app.schemas import CallSessionOut, OrderCreate, OrderIngestResponse, OrderOut
from app.services.rto_scorer import assess_rto_risk

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/orders", response_model=OrderIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_order(
    payload: OrderCreate,
    request: Request,
    db: DbDep,
    tenant: TenantDep,
) -> OrderIngestResponse:
    existing = await db.scalar(
        select(Order).where(
            Order.tenant_id == tenant.id,
            Order.external_order_id == payload.external_order_id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"order {payload.external_order_id} already exists for this tenant",
        )

    assessment = assess_rto_risk(
        raw_address=payload.raw_address,
        cod_amount=payload.cod_amount,
        max_auto_approve_cod=tenant.max_auto_approve_cod,
    )

    order = Order(
        tenant_id=tenant.id,
        external_order_id=payload.external_order_id,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        items_summary=payload.items_summary,
        cod_amount=payload.cod_amount,
        raw_address=payload.raw_address,
        delivery_window=payload.delivery_window,
        rto_risk_score=assessment.score,
        status=OrderStatus.PENDING_CALL,
    )
    db.add(order)
    await db.flush()

    call_session = CallSession(
        tenant_id=tenant.id,
        order_id=order.id,
        direction=CallDirection.OUTBOUND_VERIFY,
        status=CallStatus.ACTIVE,
        transcript=[],
        tool_traces=[],
    )
    db.add(call_session)
    await db.commit()
    await db.refresh(order)
    await db.refresh(call_session)

    return OrderIngestResponse(
        order=OrderOut.from_order(order),
        rto=assessment,
        call_session=CallSessionOut.from_session(call_session),
        session_id=call_session.id,
        ws_url=build_ws_url(request, call_session.id),
    )
