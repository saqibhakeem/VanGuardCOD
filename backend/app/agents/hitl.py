"""Database-backed human-in-the-loop approval gate."""

from __future__ import annotations

import inspect
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runtime import ApprovalDraft, EventSink
from app.db.models import (
    ApprovalRequest,
    ApprovalStatus,
    CallSession,
    CallStatus,
    Order,
    OrderStatus,
    Tenant,
)
from app.db.session import append_tool_trace, append_transcript, utcnow


def build_persistence_sink(
    call_session: CallSession, downstream: EventSink | None = None
) -> EventSink:
    """Persist transcript turns and successful tool traces as they stream."""

    async def sink(event: dict) -> None:
        event_type = event.get("event")
        if event_type == "transcript_update":
            append_transcript(
                call_session,
                str(event.get("role") or "system"),
                str(event.get("text") or ""),
            )
        elif event_type == "tool_trace" and event.get("status") != "PAUSED_FOR_APPROVAL":
            append_tool_trace(
                call_session,
                {
                    "step": event.get("step", 0),
                    "tool_name": event.get("tool_name"),
                    "arguments": event.get("arguments") or {},
                    "duration_ms": event.get("duration_ms", 0.0),
                    "status": event.get("status"),
                    "tool_call_id": event.get("tool_call_id"),
                    "approval_id": event.get("approval_id"),
                    "result": event.get("result"),
                    "error": event.get("error"),
                },
            )
        if downstream is not None:
            outcome = downstream(event)
            if inspect.isawaitable(outcome):
                await outcome

    return sink


class DatabaseApprovalGate:
    """Persist a paused tool mutation and freeze the call session for review."""

    def __init__(
        self,
        db: AsyncSession,
        tenant: Tenant,
        order: Order | None,
        call_session: CallSession,
    ) -> None:
        self.db = db
        self.tenant = tenant
        self.order = order
        self.call_session = call_session

    async def __call__(self, draft: ApprovalDraft) -> str:
        order_id = self.order.id if self.order is not None else draft.order_id
        if order_id is None:
            raise ValueError("approval draft is missing an order reference")

        from sqlalchemy import select

        # Deduplication: If a pending approval already exists for this order & tool, reuse it
        existing_pending = await self.db.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.order_id == order_id,
                ApprovalRequest.tenant_id == self.tenant.id,
                ApprovalRequest.tool_name == draft.tool_name,
                ApprovalRequest.status == ApprovalStatus.PENDING,
            ).limit(1)
        )
        if existing_pending is not None:
            return existing_pending.id

        # Deduplication: If an identical request was already rejected, do not spam with a new ticket
        existing_rejected = await self.db.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.order_id == order_id,
                ApprovalRequest.tenant_id == self.tenant.id,
                ApprovalRequest.tool_name == draft.tool_name,
                ApprovalRequest.status == ApprovalStatus.REJECTED,
            ).order_by(ApprovalRequest.created_at.desc()).limit(1)
        )
        if existing_rejected is not None:
            return existing_rejected.id

        approval = ApprovalRequest(
            id=str(uuid4()),
            tenant_id=self.tenant.id,
            order_id=order_id,
            call_session_id=self.call_session.id,
            tool_name=draft.tool_name,
            proposed_arguments=draft.arguments,
            reason=draft.reason,
            status=ApprovalStatus.PENDING,
            created_at=utcnow(),
        )
        self.db.add(approval)

        self.call_session.status = CallStatus.PAUSED_APPROVAL
        if self.order is not None and self.order.status != OrderStatus.CANCELLED:
            self.order.status = OrderStatus.NEEDS_APPROVAL

        append_tool_trace(
            self.call_session,
            {
                "step": 0,
                "tool_name": draft.tool_name,
                "arguments": draft.arguments,
                "duration_ms": 0.0,
                "status": "PAUSED_FOR_APPROVAL",
                "approval_id": approval.id,
                "reason": draft.reason,
            },
        )
        await self.db.flush()
        return approval.id
