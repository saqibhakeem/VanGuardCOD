"""Tenant-scoped order listing."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DbDep, TenantDep
from app.db.models import Order, OrderStatus
from app.schemas import OrderOut

router = APIRouter(prefix="/orders", tags=["orders"])

STATUS_PATTERN = "^(PENDING_CALL|CALLING|VERIFIED|CANCELLED|RESCHEDULED|NEEDS_APPROVAL|PENDING_RETRY|FAILED_CONTACT)$"


@router.get("", response_model=list[OrderOut])
async def list_orders(
    db: DbDep,
    tenant: TenantDep,
    status_filter: str | None = Query(default=None, alias="status", pattern=STATUS_PATTERN),
    external_order_id: str | None = Query(default=None, max_length=64),
    phone: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[OrderOut]:
    statement = (
        select(Order)
        .where(Order.tenant_id == tenant.id)
        .order_by(Order.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter is not None:
        if status_filter not in OrderStatus.ALL:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"unsupported order status: {status_filter}",
            )
        statement = statement.where(Order.status == status_filter)
    if external_order_id is not None:
        statement = statement.where(Order.external_order_id == external_order_id)
    if phone is not None:
        statement = statement.where(Order.customer_phone == phone)

    orders = (await db.scalars(statement)).all()
    return [OrderOut.from_order(order) for order in orders]


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: str, db: DbDep, tenant: TenantDep) -> OrderOut:
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.tenant_id == tenant.id)
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="order not found"
        )
    return OrderOut.from_order(order)
