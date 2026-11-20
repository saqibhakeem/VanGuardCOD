"""Phase 2 verification: parallel tools, agent runtime, and HITL approvals."""

from __future__ import annotations

import asyncio
import time

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.agents.hitl import DatabaseApprovalGate
from app.agents.inbound_rescue import build_inbound_agent
from app.agents.outbound_verifier import build_outbound_agent
from app.agents.runtime import (
    AgentProfile,
    AutonomousVoiceAgent,
    InMemoryApprovalGate,
    MockGroqClient,
    ToolCallRequest,
    ToolRegistry,
    text_completion,
    tool_call_completion,
)
from app.agents.tools import (
    INBOUND_TOOL_NAMES,
    OUTBOUND_TOOL_NAMES,
    ToolContext,
    build_tool_registry,
)
from app.db.models import (
    ApprovalRequest,
    ApprovalStatus,
    CallDirection,
    CallStatus,
    Order,
    OrderStatus,
)
from tests.conftest import TENANT_HEADERS, create_call_session


class EchoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int


async def test_parallel_tool_execution_uses_asyncio_gather():
    registry = ToolRegistry()
    both_started = asyncio.Event()
    counter = {"count": 0}

    async def handler(args: EchoArgs) -> dict:
        counter["count"] += 1
        if counter["count"] >= 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=2.0)
        return {"value": args.value}

    for name in ("echo_a", "echo_b"):
        registry.add(
            name=name,
            description=name,
            args_model=EchoArgs,
            handler=handler,
        )

    started = time.perf_counter()
    traces = await registry.execute_parallel(
        [
            ToolCallRequest(id="a", name="echo_a", arguments={"value": 1}),
            ToolCallRequest(id="b", name="echo_b", arguments={"value": 2}),
        ],
        step=3,
    )
    elapsed = time.perf_counter() - started

    assert [trace.status for trace in traces] == ["SUCCESS", "SUCCESS"]
    assert [trace.result["value"] for trace in traces] == [1, 2]
    assert all(trace.step == 3 for trace in traces)
    assert all(trace.duration_ms >= 0 for trace in traces)
    assert elapsed < 1.5


async def test_registry_rejects_invalid_and_unknown_tools():
    registry = ToolRegistry()
    calls = []

    async def handler(args: EchoArgs) -> dict:
        calls.append(args.value)
        return {"value": args.value}

    registry.add(name="echo", description="echo", args_model=EchoArgs, handler=handler)

    bad_extra = await registry.execute(
        ToolCallRequest(name="echo", arguments={"value": 1, "unexpected": True})
    )
    assert bad_extra.status == "ERROR"
    assert "validation_error" in (bad_extra.error or "")
    assert "extra_forbidden" in (bad_extra.error or "")
    assert calls == []

    unknown = await registry.execute(
        ToolCallRequest(name="missing_tool", arguments={})
    )
    assert unknown.status == "ERROR"
    assert "unknown tool" in (unknown.error or "")


async def test_approval_tool_pauses_without_executing_handler():
    registry = ToolRegistry()
    gate = InMemoryApprovalGate()
    called = {"value": False}

    async def handler(args: EchoArgs) -> dict:
        called["value"] = True
        return {"value": args.value}

    registry.add(
        name="dangerous_tool",
        description="requires review",
        args_model=EchoArgs,
        handler=handler,
        requires_approval=True,
        approval_reason="high risk mutation",
    )

    trace = await registry.execute(
        ToolCallRequest(name="dangerous_tool", arguments={"value": 9}), gate=gate
    )
    assert trace.status == "PAUSED_FOR_APPROVAL"
    assert trace.approval_id == gate.approval_ids[0]
    assert trace.arguments == {"value": 9}
    assert called["value"] is False
    assert gate.drafts[0].reason == "high risk mutation"

    bypassed = await registry.execute(
        ToolCallRequest(name="dangerous_tool", arguments={"value": 9}),
        gate=gate,
        bypass_approval=True,
    )
    assert bypassed.status == "SUCCESS"
    assert called["value"] is True


async def test_tool_registry_exposes_strict_schemas(db, tenant, seeded_order):
    call_session = await create_call_session(db, tenant, seeded_order)
    context = ToolContext(db=db, tenant=tenant, order=seeded_order, call_session=call_session)

    outbound = build_tool_registry(context, tool_names=OUTBOUND_TOOL_NAMES)
    inbound = build_tool_registry(context, tool_names=INBOUND_TOOL_NAMES)
    assert set(outbound.names) == set(OUTBOUND_TOOL_NAMES)
    assert set(inbound.names) == set(INBOUND_TOOL_NAMES)

    schemas = {
        schema["function"]["name"]: schema["function"]["parameters"]
        for schema in outbound.tool_schemas()
    }
    confirm = schemas["confirm_cod_order"]
    assert confirm["required"] == ["order_id", "verified_landmark", "delivery_window"]
    assert confirm["additionalProperties"] is False
    assert confirm["properties"]["delivery_window"]["maxLength"] == 64

    inbound_schemas = {
        schema["function"]["name"]: schema["function"]["parameters"]
        for schema in inbound.tool_schemas()
    }
    assert inbound_schemas["request_address_reroute"]["additionalProperties"] is False

    assert outbound.get("request_price_or_city_modification").requires_approval is True
    assert inbound.get("request_address_reroute").requires_approval is True


async def test_outbound_agent_confirms_low_value_order(db, tenant, seeded_order):
    seeded_order.cod_amount = 12000.0
    await db.commit()
    call_session = await create_call_session(db, tenant, seeded_order)
    agent = build_outbound_agent(db, tenant, seeded_order, call_session)

    greeting = await agent.start()
    assert "Ayesha" in greeting.text
    assert "PKR 12,000" in greeting.text

    turn = await agent.run_turn(
        "Yes, please confirm the order. Landmark is the masjid gate, tomorrow evening."
    )
    await db.commit()

    assert turn.paused is False
    assert turn.text
    assert seeded_order.status == OrderStatus.VERIFIED
    assert any(
        trace.tool_name == "confirm_cod_order" and trace.status == "SUCCESS"
        for trace in turn.tool_traces
    )
    assert call_session.status == CallStatus.ACTIVE
    assert any(entry["role"] == "user" for entry in call_session.transcript)


async def test_high_value_confirmation_pauses_and_approval_applies(db, tenant, client):
    order = await db.scalar(
        select(Order).where(Order.external_order_id == "ORD-9043")
    )
    assert order is not None
    assert order.cod_amount > tenant.max_auto_approve_cod

    call_session = await create_call_session(db, tenant, order)
    agent = build_outbound_agent(db, tenant, order, call_session)
    turn = await agent.run_turn("Yes, please confirm the order right away.")

    assert turn.paused is True
    assert len(turn.approval_ids) == 1
    approval_id = turn.approval_ids[0]
    assert order.status == OrderStatus.NEEDS_APPROVAL
    assert call_session.status == CallStatus.PAUSED_APPROVAL
    await db.commit()

    pending = await client.get("/api/v1/approvals", headers=TENANT_HEADERS)
    assert pending.status_code == 200
    assert any(item["id"] == approval_id for item in pending.json())

    response = await client.post(
        f"/api/v1/approvals/{approval_id}/resolve",
        json={"approved": True, "operator_note": "Verified on recorded line"},
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approved"] is True
    assert body["approval"]["status"] == ApprovalStatus.APPROVED
    assert body["order"]["status"] == OrderStatus.VERIFIED
    assert body["call_session"]["status"] == CallStatus.ACTIVE
    assert body["tool_result"]["status"] == OrderStatus.VERIFIED

    await db.refresh(order)
    await db.refresh(call_session)
    assert order.status == OrderStatus.VERIFIED
    assert call_session.status == CallStatus.ACTIVE
    assert any(
        entry["text"].startswith("Operator approved confirm_cod_order")
        for entry in call_session.transcript
    )

    duplicate = await client.post(
        f"/api/v1/approvals/{approval_id}/resolve",
        json={"approved": True},
        headers=TENANT_HEADERS,
    )
    assert duplicate.status_code == 409


async def test_rejected_address_change_is_not_applied(db, tenant, seeded_order, client):
    original_address = seeded_order.raw_address
    original_cod = seeded_order.cod_amount
    call_session = await create_call_session(db, tenant, seeded_order)
    agent = build_outbound_agent(db, tenant, seeded_order, call_session)

    turn = await agent.run_turn("Please change my delivery address to a different city.")
    assert turn.paused is True
    approval_id = turn.approval_ids[0]
    await db.commit()

    stored = await db.scalar(
        select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
    )
    assert stored is not None
    assert stored.tool_name == "request_price_or_city_modification"
    assert stored.status == ApprovalStatus.PENDING

    response = await client.post(
        f"/api/v1/approvals/{approval_id}/resolve",
        json={"approved": False, "operator_note": "Address change not allowed"},
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approval"]["status"] == ApprovalStatus.REJECTED
    assert body["tool_result"] is None
    assert body["order"]["raw_address"] == original_address
    assert body["order"]["cod_amount"] == original_cod
    assert body["order"]["status"] == OrderStatus.PENDING_CALL

    await db.refresh(seeded_order)
    assert seeded_order.raw_address == original_address
    assert seeded_order.status == OrderStatus.PENDING_CALL


async def test_agent_executes_multiple_scripted_tool_calls_in_one_turn():
    registry = ToolRegistry()
    invoked: list[int] = []

    async def handler(args: EchoArgs) -> dict:
        invoked.append(args.value)
        return {"value": args.value}

    for name in ("echo_a", "echo_b"):
        registry.add(
            name=name,
            description=name,
            args_model=EchoArgs,
            handler=handler,
        )

    client = MockGroqClient(
        script=[
            {
                "tool_calls": [
                    {"name": "echo_a", "arguments": {"value": 1}},
                    {"name": "echo_b", "arguments": {"value": 2}},
                ]
            },
            {"content": "All done."},
        ]
    )
    agent = AutonomousVoiceAgent(
        profile=AgentProfile(name="TestAgent", system_prompt="Test.", greeting="Hello."),
        registry=registry,
        client=client,
    )

    turn = await agent.run_turn("Run both tools in parallel.")
    assert turn.paused is False
    assert turn.text == "All done."
    assert [trace.status for trace in turn.tool_traces] == ["SUCCESS", "SUCCESS"]
    assert sorted(invoked) == [1, 2]
    assert len(turn.traces) == 2


async def test_agent_tool_validation_failure_is_reported():
    registry = ToolRegistry()

    async def handler(args: EchoArgs) -> dict:
        return {"value": args.value}

    registry.add(name="echo", description="echo", args_model=EchoArgs, handler=handler)
    client = MockGroqClient(
        script=[
            {"tool_calls": [{"name": "echo", "arguments": {"unexpected": 1}}]},
            {"content": "I need that detail again."},
        ]
    )
    agent = AutonomousVoiceAgent(
        profile=AgentProfile(name="TestAgent", system_prompt="Test.", greeting="Hello."),
        registry=registry,
        client=client,
    )

    turn = await agent.run_turn("echo something")
    assert turn.paused is False
    assert turn.tool_traces[0].status == "ERROR"
    assert "validation_error" in (turn.tool_traces[0].error or "")
    assert turn.text == "I need that detail again."


async def test_inbound_agent_logs_rider_attempt(db, tenant):
    order = await db.scalar(
        select(Order).where(Order.external_order_id == "ORD-9044")
    )
    assert order is not None
    call_session = await create_call_session(
        db, tenant, order, direction=CallDirection.INBOUND_RESCUE
    )
    agent = build_inbound_agent(db, tenant, order, call_session, caller_role="rider")

    greeting = await agent.start()
    assert "customer or the delivery rider" in greeting.text

    turn = await agent.run_turn("The gate is locked and the customer is unreachable.")
    await db.commit()

    assert turn.paused is False
    assert any(
        trace.tool_name == "log_rider_delivery_attempt" and trace.status == "SUCCESS"
        for trace in turn.tool_traces
    )
    assert any(
        "Rider delivery attempt" in entry["text"] for entry in call_session.transcript
    )


async def test_database_approval_gate_marks_session_and_order(db, tenant, seeded_order):
    seeded_order.cod_amount = 50000.0
    call_session = await create_call_session(db, tenant, seeded_order)
    gate = DatabaseApprovalGate(db, tenant, seeded_order, call_session)

    from app.agents.runtime import ApprovalDraft

    approval_id = await gate(
        ApprovalDraft(
            tool_name="confirm_cod_order",
            arguments={
                "order_id": seeded_order.id,
                "verified_landmark": "Near the park",
                "delivery_window": "Tomorrow",
            },
            reason="COD above threshold",
        )
    )
    await db.commit()

    approval = await db.scalar(
        select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
    )
    assert approval is not None
    assert approval.status == ApprovalStatus.PENDING
    assert approval.proposed_arguments["verified_landmark"] == "Near the park"
    assert seeded_order.status == OrderStatus.NEEDS_APPROVAL
    assert call_session.status == CallStatus.PAUSED_APPROVAL
    assert call_session.tool_traces[-1]["approval_id"] == approval_id


async def test_approval_endpoints_validate_requests(client):
    missing = await client.post(
        "/api/v1/approvals/does-not-exist/resolve",
        json={"approved": True},
        headers=TENANT_HEADERS,
    )
    assert missing.status_code == 404

    extra_field = await client.post(
        "/api/v1/approvals/does-not-exist/resolve",
        json={"approved": True, "unexpected": "x"},
        headers=TENANT_HEADERS,
    )
    assert extra_field.status_code == 422

    bad_status = await client.get(
        "/api/v1/approvals", params={"status": "WHATEVER"}, headers=TENANT_HEADERS
    )
    assert bad_status.status_code == 422
