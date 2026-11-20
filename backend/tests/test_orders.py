"""Phase 1 verification: order ingestion, RTO scoring, and tenant isolation."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import CallSession, Order, Tenant
from app.security import hash_api_key
from app.services.rto_scorer import (
    assess_rto_risk,
    calculate_rto_risk_score,
    identify_missing_address_components,
)
from tests.conftest import TENANT_HEADERS


async def test_seed_data_has_tenant_and_four_orders(client, db, tenant):
    assert tenant.name == "Karachi Threads & Textiles"
    assert tenant.max_auto_approve_cod == 25000.0

    orders = (await db.scalars(select(Order).order_by(Order.external_order_id))).all()
    assert len(orders) == 4
    scores = {order.external_order_id: order.rto_risk_score for order in orders}
    assert scores == {
        "ORD-9042": 33,
        "ORD-9043": 45,
        "ORD-9044": 84,
        "ORD-9045": 70,
    }

    response = await client.get("/api/v1/orders", headers=TENANT_HEADERS)
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 4
    assert payload[0]["external_order_id"] in scores


async def test_webhook_ingests_order_and_queues_outbound_session(client):
    payload = {
        "external_order_id": "ORD-9100",
        "customer_name": "Sana Malik",
        "customer_phone": "0301 234 5678",
        "items_summary": "2x Cotton Kurti",
        "cod_amount": 5000,
        "raw_address": "House 12, Street 4, Block C, North Nazimabad, Karachi",
        "delivery_window": "Tomorrow 5 PM",
    }
    response = await client.post(
        "/api/v1/webhooks/orders", json=payload, headers=TENANT_HEADERS
    )
    assert response.status_code == 201
    body = response.json()

    assert body["order"]["external_order_id"] == "ORD-9100"
    assert body["order"]["customer_phone"] == "+923012345678"
    assert body["order"]["rto_risk_score"] == 25
    assert body["order"]["status"] == "PENDING_CALL"
    assert body["rto"]["score"] == 25
    assert body["rto"]["has_house_number"] is True
    assert body["rto"]["missing_components"] == ["verified_landmark"]
    assert body["call_session"]["direction"] == "OUTBOUND_VERIFY"
    assert body["session_id"] == body["call_session"]["id"]
    assert body["ws_url"].endswith(f"/ws/call/{body['session_id']}")

    listing = await client.get("/api/v1/orders", headers=TENANT_HEADERS)
    assert len(listing.json()) == 5


async def test_webhook_rejects_duplicate_order(client):
    payload = {
        "external_order_id": "ORD-9042",
        "customer_name": "Ayesha Khan",
        "customer_phone": "+923001234567",
        "items_summary": "1x Lawn Kurta",
        "cod_amount": 4500,
        "raw_address": "House 42, Street 7, Gulshan-e-Iqbal, Karachi",
    }
    response = await client.post(
        "/api/v1/webhooks/orders", json=payload, headers=TENANT_HEADERS
    )
    assert response.status_code == 409


async def test_webhook_scores_incomplete_address_as_high_risk(client):
    payload = {
        "external_order_id": "ORD-9200",
        "customer_name": "Imran Shah",
        "customer_phone": "0345-111-2233",
        "items_summary": "1x Wash and Wear Suit",
        "cod_amount": 1000,
        "raw_address": "Near Sunday Bazaar",
    }
    response = await client.post(
        "/api/v1/webhooks/orders", json=payload, headers=TENANT_HEADERS
    )
    assert response.status_code == 201
    rto = response.json()["rto"]
    assert rto["score"] == 76
    assert rto["is_high_risk"] is True
    assert rto["has_house_number"] is False
    assert rto["address_word_count"] == 3
    assert rto["missing_components"] == [
        "house_or_plot_number",
        "street_or_area_detail",
        "city",
        "verified_landmark",
    ]


async def test_invalid_phone_and_non_cod_payloads_are_rejected(client):
    base_payload = {
        "external_order_id": "ORD-9300",
        "customer_name": "Test Buyer",
        "customer_phone": "not-a-phone",
        "items_summary": "1x Item",
        "cod_amount": 1000,
        "raw_address": "House 1, Street 2, Gulshan, Karachi",
    }
    response = await client.post(
        "/api/v1/webhooks/orders", json=base_payload, headers=TENANT_HEADERS
    )
    assert response.status_code == 422

    prepaid = {**base_payload, "customer_phone": "+923001112233", "payment_method": "CARD"}
    response = await client.post(
        "/api/v1/webhooks/orders", json=prepaid, headers=TENANT_HEADERS
    )
    assert response.status_code == 422


async def test_orders_are_isolated_per_tenant(client, db):
    other_tenant = Tenant(
        name="Lahore Leather Works",
        api_key_hash=hash_api_key("lahore_demo_key_2026"),
        max_auto_approve_cod=40000.0,
    )
    db.add(other_tenant)
    await db.flush()
    other_order = Order(
        tenant_id=other_tenant.id,
        external_order_id="LLW-1001",
        customer_name="Other Buyer",
        customer_phone="+923009998877",
        items_summary="1x Leather Bag",
        cod_amount=6000,
        raw_address="House 8, Street 2, Model Town, Lahore",
        rto_risk_score=25,
        status="PENDING_CALL",
    )
    db.add(other_order)
    await db.commit()

    other_headers = {"X-Tenant-API-Key": "lahore_demo_key_2026"}
    response = await client.get("/api/v1/orders", headers=other_headers)
    assert response.status_code == 200
    assert [item["external_order_id"] for item in response.json()] == ["LLW-1001"]

    default_listing = await client.get("/api/v1/orders", headers=TENANT_HEADERS)
    references = [item["external_order_id"] for item in default_listing.json()]
    assert "LLW-1001" not in references

    cross_tenant_fetch = await client.get(
        f"/api/v1/orders/{other_order.id}", headers=TENANT_HEADERS
    )
    assert cross_tenant_fetch.status_code == 404

    invalid_key = await client.get(
        "/api/v1/orders", headers={"X-Tenant-API-Key": "unknown-key"}
    )
    assert invalid_key.status_code == 401


async def test_order_status_filter_and_lookup(client):
    response = await client.get(
        "/api/v1/orders", params={"status": "CANCELLED"}, headers=TENANT_HEADERS
    )
    assert response.status_code == 200
    assert response.json() == []

    seeded = await client.get(
        "/api/v1/orders",
        params={"external_order_id": "ORD-9044"},
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 200
    assert seeded.json()[0]["customer_name"] == "Hina Raza"

    bad_status = await client.get(
        "/api/v1/orders", params={"status": "UNKNOWN"}, headers=TENANT_HEADERS
    )
    assert bad_status.status_code == 422


async def test_trigger_outbound_reuses_active_session(client):
    listing = await client.get(
        "/api/v1/orders",
        params={"external_order_id": "ORD-9042"},
        headers=TENANT_HEADERS,
    )
    order_id = listing.json()[0]["id"]

    first = await client.post(
        f"/api/v1/calls/trigger-outbound/{order_id}", headers=TENANT_HEADERS
    )
    assert first.status_code == 201
    session_id = first.json()["session_id"]
    assert first.json()["direction"] == "OUTBOUND_VERIFY"
    assert first.json()["order"]["status"] == "CALLING"

    second = await client.post(
        f"/api/v1/calls/trigger-outbound/{order_id}", headers=TENANT_HEADERS
    )
    assert second.status_code == 201
    assert second.json()["session_id"] == session_id


async def test_start_inbound_by_caller_phone(client, db):
    response = await client.post(
        "/api/v1/calls/start-inbound",
        json={"caller_phone": "+923214567890", "caller_role": "rider"},
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["direction"] == "INBOUND_RESCUE"
    assert body["order"]["external_order_id"] == "ORD-9043"

    call_session = await db.scalar(
        select(CallSession).where(CallSession.id == body["session_id"])
    )
    assert call_session is not None
    assert call_session.transcript[0]["text"] == "inbound caller role: rider"

    unknown = await client.post(
        "/api/v1/calls/start-inbound",
        json={"caller_phone": "+923000000000"},
        headers=TENANT_HEADERS,
    )
    assert unknown.status_code == 404


async def test_pending_outbound_listing_and_decline(client):
    listing = await client.get(
        "/api/v1/orders",
        params={"external_order_id": "ORD-9042"},
        headers=TENANT_HEADERS,
    )
    order_id = listing.json()[0]["id"]

    trigger = await client.post(
        f"/api/v1/calls/trigger-outbound/{order_id}", headers=TENANT_HEADERS
    )
    assert trigger.status_code == 201
    session_id = trigger.json()["session_id"]

    pending = await client.get("/api/v1/calls/pending-outbound", headers=TENANT_HEADERS)
    assert pending.status_code == 200
    assert [item["session_id"] for item in pending.json()] == [session_id]
    assert pending.json()[0]["ws_url"].endswith(f"/ws/call/{session_id}")

    declined = await client.post(
        f"/api/v1/calls/{session_id}/decline", headers=TENANT_HEADERS
    )
    assert declined.status_code == 200
    assert declined.json() == {"session_id": session_id, "status": "COMPLETED"}

    after = await client.get("/api/v1/calls/pending-outbound", headers=TENANT_HEADERS)
    assert after.json() == []

    order = await client.get(f"/api/v1/orders/{order_id}", headers=TENANT_HEADERS)
    assert order.json()["status"] == "PENDING_CALL"

    missing = await client.post(
        "/api/v1/calls/unknown-session/decline", headers=TENANT_HEADERS
    )
    assert missing.status_code == 404


async def test_pending_outbound_ignores_answered_sessions(
    client, db, seeded_order, tenant
):
    from tests.conftest import create_call_session

    answered = await create_call_session(db, tenant, seeded_order)
    answered.transcript = [
        {"role": "assistant", "text": "Greeting already delivered.", "timestamp_ms": 0}
    ]
    await db.commit()

    pending = await client.get("/api/v1/calls/pending-outbound", headers=TENANT_HEADERS)
    assert pending.status_code == 200
    assert pending.json() == []


def test_rto_scorer_formula_and_clamping():
    assert calculate_rto_risk_score("", 0.0, 25000.0) == 75
    assert calculate_rto_risk_score("House 1 Karachi", 25000.0, 25000.0) == 70
    assert calculate_rto_risk_score("House 1 Karachi", 100000.0, 25000.0) == 70
    assert calculate_rto_risk_score("House 1 Street 2 Block A Karachi", 25000.0, 25000.0) == 45
    assert calculate_rto_risk_score("House 1 Street 2 Block A Karachi", 0.0, 0.0) == 20

    assessment = assess_rto_risk("House 1 Street 2 Block A Karachi", 12500.0, 25000.0, "Near park")
    assert assessment.score == 33
    assert assessment.cod_factor == 0.5
    assert assessment.factors["cod_amount"] == 12.5
    assert assessment.missing_components == []

    missing = identify_missing_address_components("Shop 5, Saddar")
    assert "city" in missing
    assert "street_or_area_detail" in missing
    assert "verified_landmark" in missing
