"""Async SQLAlchemy 2.0 models matching the TRD schema."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class OrderStatus:
    PENDING_CALL = "PENDING_CALL"
    CALLING = "CALLING"
    VERIFIED = "VERIFIED"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"

    ALL = (
        PENDING_CALL,
        CALLING,
        VERIFIED,
        CANCELLED,
        RESCHEDULED,
        NEEDS_APPROVAL,
    )


class CallDirection:
    OUTBOUND_VERIFY = "OUTBOUND_VERIFY"
    INBOUND_RESCUE = "INBOUND_RESCUE"


class CallStatus:
    ACTIVE = "ACTIVE"
    PAUSED_APPROVAL = "PAUSED_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ApprovalStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    default_language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    voice_persona: Mapped[str] = mapped_column(String(32), default="troy", nullable=False)
    max_auto_approve_cod: Mapped[float] = mapped_column(Float, default=25000.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    orders: Mapped[list["Order"]] = relationship(back_populates="tenant")
    call_sessions: Mapped[list["CallSession"]] = relationship(back_populates="tenant")
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(back_populates="tenant")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), index=True, nullable=False
    )
    external_order_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    items_summary: Mapped[str] = mapped_column(Text, nullable=False)
    cod_amount: Mapped[float] = mapped_column(Float, nullable=False)
    raw_address: Mapped[str] = mapped_column(Text, nullable=False)
    verified_landmark: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_window: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rto_risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(32), index=True, nullable=False, default=OrderStatus.PENDING_CALL
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="orders")
    call_sessions: Mapped[list["CallSession"]] = relationship(back_populates="order")
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(back_populates="order")


class CallSession(Base):
    __tablename__ = "call_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), index=True, nullable=False
    )
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orders.id"), index=True, nullable=False
    )
    direction: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=CallStatus.ACTIVE)
    avg_turn_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    transcript: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    tool_traces: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="call_sessions")
    order: Mapped[Order] = relationship(back_populates="call_sessions")
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(
        back_populates="call_session"
    )


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), index=True, nullable=False
    )
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orders.id"), index=True, nullable=False
    )
    call_session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("call_sessions.id"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    proposed_arguments: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ApprovalStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="approval_requests")
    order: Mapped[Order] = relationship(back_populates="approval_requests")
    call_session: Mapped[CallSession] = relationship(back_populates="approval_requests")
