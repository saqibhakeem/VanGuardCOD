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
    call_attempts: int = 0
    max_call_attempts: int = 3
    next_retry_at: datetime | None = None
    last_call_at: datetime | None = None
    verification_channel: str | None = None
    provider_reference_id: str | None = None
    delivery_status: str | None = None
    created_at: datetime

    @field_validator("created_at", "next_retry_at", "last_call_at", mode="before")
    @classmethod
    def _datetime_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None

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
    channel_choice: str = "BOTH"
    twilio_account_sid: str | None = None
    twilio_from_number: str | None = None
    whatsapp_provider: str = "META"
    whatsapp_phone_number_id: str | None = None
    whatsapp_waba_id: str | None = None
    omnichannel_strategy: str = "WHATSAPP_FIRST"
    is_twilio_verified: bool = False
    is_whatsapp_verified: bool = False
    has_twilio_auth_token: bool = False
    has_whatsapp_access_token: bool = False

    @model_validator(mode="before")
    @classmethod
    def _extract_token_presence(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "has_twilio_auth_token" not in data:
                data["has_twilio_auth_token"] = bool(data.get("twilio_auth_token"))
            if "has_whatsapp_access_token" not in data:
                data["has_whatsapp_access_token"] = bool(data.get("whatsapp_access_token"))
            return data
        # Object attribute extraction
        has_tw = bool(getattr(data, "twilio_auth_token", None))
        has_wa = bool(getattr(data, "whatsapp_access_token", None))
        setattr(data, "has_twilio_auth_token", has_tw)
        setattr(data, "has_whatsapp_access_token", has_wa)
        return data


class ChannelConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_choice: Literal["TWILIO", "WHATSAPP", "BOTH"] = "BOTH"
    twilio_account_sid: str | None = Field(default=None, max_length=64)
    twilio_auth_token: str | None = Field(default=None, max_length=128)
    twilio_from_number: str | None = Field(default=None, max_length=32)
    whatsapp_provider: Literal["META", "TWILIO"] = "META"
    whatsapp_phone_number_id: str | None = Field(default=None, max_length=64)
    whatsapp_access_token: str | None = Field(default=None, max_length=4000)
    whatsapp_waba_id: str | None = Field(default=None, max_length=64)
    whatsapp_verify_token: str | None = Field(default=None, max_length=64)
    omnichannel_strategy: Literal["WHATSAPP_FIRST", "VOICE_FIRST"] = "WHATSAPP_FIRST"


class ChannelConfigOut(BaseModel):
    channel_choice: str
    twilio_account_sid: str | None
    twilio_from_number: str | None
    has_twilio_auth_token: bool
    is_twilio_verified: bool
    whatsapp_provider: str
    whatsapp_phone_number_id: str | None
    whatsapp_waba_id: str | None
    has_whatsapp_access_token: bool
    is_whatsapp_verified: bool
    omnichannel_strategy: str


class TestTwilioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    account_sid: str = Field(min_length=10, max_length=64)
    auth_token: str = Field(min_length=10, max_length=128)
    from_number: str | None = Field(default=None, max_length=32)


class TestTwilioResponse(BaseModel):
    ok: bool
    friendly_name: str | None = None
    account_status: str | None = None
    error: str | None = None


class TestWhatsAppRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider: Literal["META", "TWILIO"] = "META"
    phone_number_id: str | None = Field(default=None, max_length=64)
    access_token: str | None = Field(default=None, max_length=4000)
    waba_id: str | None = Field(default=None, max_length=64)
    twilio_account_sid: str | None = Field(default=None, max_length=64)
    twilio_auth_token: str | None = Field(default=None, max_length=128)
    twilio_whatsapp_from: str | None = Field(default=None, max_length=32)


class TestWhatsAppResponse(BaseModel):
    ok: bool
    display_phone_number: str | None = None
    verified_name: str | None = None
    quality_rating: str | None = None
    error: str | None = None


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
    store_name: str | None = None
    channel: str = "VOICE"
    provider_reference_id: str | None = None


class CallDeclineResponse(BaseModel):
    session_id: str
    status: str


class CallTimeoutResponse(BaseModel):
    session_id: str
    status: str
    order_id: str
    order_status: str
    call_attempts: int
    max_call_attempts: int
    next_retry_at: datetime | None = None

    @field_validator("next_retry_at", mode="before")
    @classmethod
    def _next_retry_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None


class RetryDispatchResponse(BaseModel):
    dispatched_count: int
    orders_retried: list[str]


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


class UserOut(BaseModel):
    id: str
    username: str
    name: str
    role: str
    role_label: str
    permissions: list[str]
    tenant_id: str
    tenant_name: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    tenant_key: str | None = Field(default=None, max_length=128)


class LoginResponse(BaseModel):
    token: str
    user: UserOut


class RegisterStoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    store_name: str = Field(min_length=2, max_length=120)
    admin_username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, max_length=128)
    default_language: str = Field(default="en", max_length=10)
    voice_persona: str = Field(default="troy", max_length=32)
    max_auto_approve_cod: float = Field(default=25000.0, ge=0.0)
    contact_phone: str | None = Field(default=None, max_length=32)
    channel_choice: Literal["TWILIO", "WHATSAPP", "BOTH"] = "BOTH"
    twilio_account_sid: str | None = Field(default=None, max_length=64)
    twilio_auth_token: str | None = Field(default=None, max_length=128)
    twilio_from_number: str | None = Field(default=None, max_length=32)
    whatsapp_provider: Literal["META", "TWILIO"] = "META"
    whatsapp_phone_number_id: str | None = Field(default=None, max_length=64)
    whatsapp_access_token: str | None = Field(default=None, max_length=4000)
    whatsapp_waba_id: str | None = Field(default=None, max_length=64)
    omnichannel_strategy: Literal["WHATSAPP_FIRST", "VOICE_FIRST"] = "WHATSAPP_FIRST"


class RegisterStoreResponse(BaseModel):
    token: str
    api_key: str
    tenant: TenantOut
    user: UserOut
    webhook_url: str


