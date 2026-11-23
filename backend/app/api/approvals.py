"""Human-in-the-loop approval review and resolution endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agents.runtime import ToolCallRequest
from app.agents.tools import ToolContext, build_tool_registry
from app.api.deps import DbDep, TenantDep
from app.db.models import (
    ApprovalRequest,
    ApprovalStatus,
    CallSession,
    CallStatus,
    Order,
    OrderStatus,
)
from app.db.session import append_tool_trace, append_transcript
from app.schemas import (
    ApprovalOut,
    CallSessionOut,
    OrderOut,
    ResolveApprovalRequest,
    ResolveApprovalResponse,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    db: DbDep,
    tenant: TenantDep,
    status_filter: str = Query(default=ApprovalStatus.PENDING, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ApprovalOut]:
    statement = (
        select(ApprovalRequest)
        .options(selectinload(ApprovalRequest.order))
        .where(ApprovalRequest.tenant_id == tenant.id)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter.upper() != "ALL":
        if status_filter.upper() not in {
            ApprovalStatus.PENDING,
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
        }:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"unsupported approval status: {status_filter}",
            )
        statement = statement.where(ApprovalRequest.status == status_filter.upper())

    approvals = (await db.scalars(statement)).all()
    return [ApprovalOut.from_approval(approval) for approval in approvals]


@router.post("/{approval_id}/resolve", response_model=ResolveApprovalResponse)
async def resolve_approval(
    approval_id: str,
    payload: ResolveApprovalRequest,
    db: DbDep,
    tenant: TenantDep,
) -> ResolveApprovalResponse:
    approval = await db.scalar(
        select(ApprovalRequest)
        .options(
            selectinload(ApprovalRequest.order),
            selectinload(ApprovalRequest.call_session),
        )
        .where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.tenant_id == tenant.id,
        )
    )
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="approval request not found"
        )
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"approval request already {approval.status.lower()}",
        )

    order = approval.order
    call_session = approval.call_session
    if order is None or call_session is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="approval request is missing its order or call session",
        )
    if order.tenant_id != tenant.id or call_session.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="approval request not found"
        )

    tool_result: dict | None = None
    resolution_note = payload.operator_note or (
        "approved by operator" if payload.approved else "rejected by operator"
    )

    if payload.approved:
        try:
            registry = build_tool_registry(
                ToolContext(
                    db=db, tenant=tenant, order=order, call_session=call_session
                ),
                tool_names=[approval.tool_name],
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

        trace = await registry.execute(
            ToolCallRequest(
                name=approval.tool_name,
                arguments=dict(approval.proposed_arguments),
            ),
            step=0,
            bypass_approval=True,
        )
        if trace.status != "SUCCESS":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"tool execution failed: {trace.error}",
            )

        tool_result = trace.result
        approval.status = ApprovalStatus.APPROVED
        call_session.status = CallStatus.ACTIVE
        append_transcript(
            call_session,
            "system",
            f"Operator approved {approval.tool_name}: {resolution_note}",
        )
        append_tool_trace(
            call_session,
            {
                "step": 0,
                "tool_name": approval.tool_name,
                "arguments": dict(approval.proposed_arguments),
                "duration_ms": trace.duration_ms,
                "status": "SUCCESS",
                "approval_id": approval.id,
                "result": trace.result,
            },
        )
    else:
        approval.status = ApprovalStatus.REJECTED
        call_session.status = CallStatus.ACTIVE
        if order.status == OrderStatus.NEEDS_APPROVAL:
            order.status = OrderStatus.PENDING_CALL
        append_transcript(
            call_session,
            "system",
            f"Operator rejected {approval.tool_name}: {resolution_note}",
        )
        append_tool_trace(
            call_session,
            {
                "step": 0,
                "tool_name": approval.tool_name,
                "arguments": dict(approval.proposed_arguments),
                "duration_ms": 0.0,
                "status": "REJECTED",
                "approval_id": approval.id,
                "reason": resolution_note,
            },
        )

    # If this approval is for a WhatsApp verification session, notify the customer immediately
    try:
        from app.services.whatsapp_agent import notify_customer_approval_resolution
        await notify_customer_approval_resolution(
            approval=approval,
            approved=payload.approved,
            resolution_note=resolution_note,
            db=db,
        )
    except Exception as notify_err:
        import logging
        logging.getLogger(__name__).warning("Failed to dispatch WhatsApp resolution notice: %s", notify_err)

    await db.commit()
    await db.refresh(approval)
    await db.refresh(order)
    await db.refresh(call_session)

    return ResolveApprovalResponse(
        approval=ApprovalOut.from_approval(approval, order),
        approved=payload.approved,
        order=OrderOut.from_order(order),
        call_session=CallSessionOut.from_session(call_session),
        tool_result=tool_result,
    )
