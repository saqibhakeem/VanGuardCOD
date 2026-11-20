"""Pydantic v2 request and response contracts for the REST API."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models import ApprovalRequest, CallSession, Order, Tenant
from app.security import normalize_phone
from app.services.rto_scorer import RtoAssessment

PHONE_PATTERN = r"^\+[1-9]\d{6,14}$"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    external_order_id: str = Field(min_length=1, max_length=64)
    customer_name: str = Field(min_length=1, max_length=120)
    customer_phone: str = Field(min_length=7, max_length=32)
    items_summary: str = Field(min_length=1, max_length=2000)
    cod_amount: float = Field(ge=0.0)
    raw_address: str = Field(min_length=3, max_length=2000)
    delivery_window: str | None = Field(default=None, max_length=64)
    payment_method: str = Field(default="COD", max_length=24)

    @field_validator("customer_phone")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        normalized = normalize_phone(value)
        if not re.match(PHONE_PATTERN, normalized):
            raise ValueError("customer_phone must be a valid E.164 phone number")
        return normalized

    @model_validator(mode="after")
    def _require_cod(self) -> "OrderCreate":
        if self.payment_method.strip().upper() not in {"COD", "CASH ON DELIVERY"}:
            raise ValueError("only Cash-on-Delivery orders are supported")
        return self


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    external_order_id: str
    customer_name: str
    customer_phone: str
    items_summary: str
    cod_amount: float
    raw_address: str
    verified_landmark: str | None
    delivery_window: str | None
    rto_risk_score: int
    status: str
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _created_at_utc(cls, value: datetime) -> datetime:
        return _as_utc(value) or value

    @classmethod
    def from_order(cls, order: Order) -> "OrderOut":
        return cls.model_validate(order)


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    default_language: str
    voice_persona: str
    max_auto_approve_cod: float


class RuntimeConfigOut(BaseModel):
    tenant: TenantOut
    environment: str
    api_prefix: str
    mock_mode: bool
    stt_model: str
    llm_model: str
    fast_llm_model: str
    tts_model: str
    tts_default_voice: str
    stt_language: str
    llm_temperature: float
    call_reconnect_grace_seconds: float


class CallSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    order_id: str
    direction: str
    status: str
    avg_turn_latency_ms: float
    transcript: list[dict[str, Any]]
    tool_traces: list[dict[str, Any]]
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _created_at_utc(cls, value: datetime) -> datetime:
        return _as_utc(value) or value

    @classmethod
    def from_session(cls, session: CallSession) -> "CallSessionOut":
        return cls.model_validate(session)


class CallSessionSummaryOut(BaseModel):
    id: str
    order_id: str
    external_order_id: str
    customer_name: str
    direction: str
    status: str
    avg_turn_latency_ms: float
    turn_count: int
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _created_at_utc(cls, value: datetime) -> datetime:
        return _as_utc(value) or value


class OrderIngestResponse(BaseModel):
    order: OrderOut
    rto: RtoAssessment
    call_session: CallSessionOut
    session_id: str
    ws_url: str


class CallTriggerResponse(BaseModel):
    session_id: str
    ws_url: str
    direction: str
    status: str
    order: OrderOut


class CallDeclineResponse(BaseModel):
    session_id: str
    status: str


class InboundStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    order_id: str | None = Field(default=None, max_length=36)
    caller_phone: str | None = Field(default=None, max_length=32)
    caller_role: Literal["customer", "rider"] = "customer"

    @field_validator("caller_phone")
    @classmethod
    def _normalize_optional_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value else None


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    order_id: str
    call_session_id: str
    tool_name: str
    proposed_arguments: dict[str, Any]
    reason: str
    status: str
    created_at: datetime
    current_values: dict[str, Any] = Field(default_factory=dict)
    order_reference: str | None = None

    @field_validator("created_at", mode="before")
    @classmethod
    def _created_at_utc(cls, value: datetime) -> datetime:
        return _as_utc(value) or value

    @classmethod
    def from_approval(cls, approval: ApprovalRequest, order: Order | None = None) -> "ApprovalOut":
        resolved_order = order or approval.order
        current_values: dict[str, Any] = {}
        order_reference: str | None = None
        if resolved_order is not None:
            current_values = {
                "raw_address": resolved_order.raw_address,
                "cod_amount": resolved_order.cod_amount,
                "delivery_window": resolved_order.delivery_window,
                "verified_landmark": resolved_order.verified_landmark,
                "status": resolved_order.status,
            }
            order_reference = resolved_order.external_order_id
        return cls(
            id=approval.id,
            tenant_id=approval.tenant_id,
            order_id=approval.order_id,
            call_session_id=approval.call_session_id,
            tool_name=approval.tool_name,
            proposed_arguments=approval.proposed_arguments,
            reason=approval.reason,
            status=approval.status,
            created_at=approval.created_at,
            current_values=current_values,
            order_reference=order_reference,
        )


class ResolveApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    approved: bool
    operator_note: str | None = Field(default=None, max_length=1000)


class ResolveApprovalResponse(BaseModel):
    approval: ApprovalOut
    approved: bool
    order: OrderOut
    call_session: CallSessionOut
    tool_result: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    tenant: str | None = None
