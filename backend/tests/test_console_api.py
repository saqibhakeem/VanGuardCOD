"""Console support endpoints: runtime config and call session summaries."""

from __future__ import annotations

from app.db.models import Order, Tenant
from app.security import hash_api_key
from tests.conftest import TENANT_HEADERS, create_call_session


async def test_runtime_config_is_sanitized(client):
    response = await client.get("/api/v1/config", headers=TENANT_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["tenant"]["name"] == "Karachi Threads & Textiles"
    assert body["tenant"]["max_auto_approve_cod"] == 25000.0
    assert body["mock_mode"] is True
    assert body["stt_model"] == "whisper-large-v3-turbo"
    assert body["tts_model"] == "canopylabs/orpheus-v1-english"
    assert body["call_reconnect_grace_seconds"] == 30.0
    assert "api_key" not in body
    assert "groq" not in response.text.lower()


async def test_runtime_config_requires_a_valid_tenant(client):
    response = await client.get(
        "/api/v1/config", headers={"X-Tenant-API-Key": "unknown-key"}
    )

    assert response.status_code == 401


async def test_call_session_listing_reports_order_and_turn_count(
    client, db, seeded_order, tenant
):
    empty = await client.get("/api/v1/calls/sessions", headers=TENANT_HEADERS)
    assert empty.status_code == 200
    assert empty.json() == []

    session = await create_call_session(db, tenant, seeded_order)
    session.transcript = [
        {"role": "assistant", "text": "Greeting", "timestamp_ms": 0},
        {"role": "user", "text": "Confirm it", "timestamp_ms": 800},
        {"role": "system", "text": "note", "timestamp_ms": 900},
    ]
    session.avg_turn_latency_ms = 412.5
    await db.commit()

    response = await client.get("/api/v1/calls/sessions", headers=TENANT_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == session.id
    assert body[0]["external_order_id"] == seeded_order.external_order_id
    assert body[0]["customer_name"] == seeded_order.customer_name
    assert body[0]["direction"] == "OUTBOUND_VERIFY"
    assert body[0]["avg_turn_latency_ms"] == 412.5
    assert body[0]["turn_count"] == 2

    invalid = await client.get(
        "/api/v1/calls/sessions", params={"limit": 0}, headers=TENANT_HEADERS
    )
    assert invalid.status_code == 422


async def test_call_session_listing_is_tenant_scoped(client, db):
    other_tenant = Tenant(
        name="Lahore Leather Works",
        api_key_hash=hash_api_key("lahore_demo_key_2026"),
        max_auto_approve_cod=40000.0,
    )
    db.add(other_tenant)
    await db.flush()
    other_order = Order(
        tenant_id=other_tenant.id,
        external_order_id="LLW-2001",
        customer_name="Other Buyer",
        customer_phone="+923009998877",
        items_summary="1x Leather Bag",
        cod_amount=6000,
        raw_address="House 8, Street 2, Model Town, Lahore",
        rto_risk_score=25,
        status="PENDING_CALL",
    )
    db.add(other_order)
    await db.flush()
    await create_call_session(db, other_tenant, other_order)

    response = await client.get("/api/v1/calls/sessions", headers=TENANT_HEADERS)
    assert response.status_code == 200
    assert response.json() == []


async def test_console_static_mount_serves_spa(client):
    response = await client.get("/console/", follow_redirects=True)
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "VanguardCOD" in response.text
    assert "/console/assets/" in response.text

