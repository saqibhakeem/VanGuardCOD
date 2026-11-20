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


async def test_auth_login_and_roles(client):
    bad = await client.post(
        "/api/v1/auth/login", json={"username": "operator", "password": "wrong"}
    )
    assert bad.status_code == 401

    op_res = await client.post(
        "/api/v1/auth/login",
        json={"username": "operator", "password": "operator123"},
    )
    assert op_res.status_code == 200
    op_body = op_res.json()
    assert op_body["user"]["role"] == "VERIFICATION_OFFICER"
    assert "orders.view" in op_body["user"]["permissions"]

    mgr_res = await client.post(
        "/api/v1/auth/login",
        json={"username": "manager", "password": "manager123"},
    )
    assert mgr_res.status_code == 200
    assert mgr_res.json()["user"]["role"] == "LOGISTICS_MANAGER"

    me = await client.get("/api/v1/auth/me", headers={"X-User-Role": "manager"})
    assert me.status_code == 200
    assert me.json()["role"] == "LOGISTICS_MANAGER"

    # Backward compatibility header
    me_legacy = await client.get("/api/v1/auth/me", headers={"X-SAP-Role": "manager"})
    assert me_legacy.status_code == 200
    assert me_legacy.json()["role"] == "LOGISTICS_MANAGER"


async def test_auth_store_registration(client):
    reg_payload = {
        "store_name": "Al-Karam Test Boutique",
        "admin_username": "alkaram_admin",
        "password": "securepassword123",
        "default_language": "ur",
        "voice_persona": "hannah",
        "max_auto_approve_cod": 35000.0,
        "contact_phone": "+923001122334",
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 200
    reg_body = reg_res.json()
    assert reg_body["tenant"]["name"] == "Al-Karam Test Boutique"
    assert reg_body["tenant"]["max_auto_approve_cod"] == 35000.0
    assert reg_body["api_key"].startswith("vcod_")
    assert "/api/v1/webhooks/orders" in reg_body["webhook_url"]

    dup_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert dup_res.status_code == 409

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"username": "alkaram_admin", "password": "securepassword123"},
    )
    assert login_res.status_code == 200
    assert login_res.json()["user"]["tenant_name"] == "Al-Karam Test Boutique"


async def test_cross_tenant_pending_outbound_and_simulator_ringing(client):
    reg_payload = {
        "store_name": "Gul Ahmed Fabrics",
        "admin_username": "gulahmed_owner",
        "password": "password123",
        "default_language": "en",
        "voice_persona": "troy",
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 200
    new_api_key = reg_res.json()["api_key"]
    headers = {"X-Tenant-API-Key": new_api_key}

    order_payload = {
        "external_order_id": "ORD-GUL-99",
        "customer_name": "Farhan Saeed",
        "customer_phone": "+923009998877",
        "items_summary": "Luxury Lawn Stitched 3-Piece",
        "cod_amount": 7500.0,
        "raw_address": "House 55, Street 10, DHA Phase 5, Lahore",
        "payment_method": "COD",
    }
    ingest_res = await client.post(
        "/api/v1/webhooks/orders", json=order_payload, headers=headers
    )
    assert ingest_res.status_code == 201
    order_data = ingest_res.json()
    order_id = order_data["order"]["id"]

    trig_res = await client.post(
        f"/api/v1/calls/trigger-outbound/{order_id}", headers=headers
    )
    assert trig_res.status_code == 201
    session_id = trig_res.json()["session_id"]
    assert trig_res.json()["store_name"] == "Gul Ahmed Fabrics"

    # Customer phone simulator polls without ANY tenant header
    phone_res = await client.get("/api/v1/calls/pending-outbound")
    assert phone_res.status_code == 200
    pending_calls = phone_res.json()
    assert len(pending_calls) >= 1
    target_call = next(c for c in pending_calls if c["session_id"] == session_id)
    assert target_call["store_name"] == "Gul Ahmed Fabrics"
    assert target_call["order"]["customer_name"] == "Farhan Saeed"
    assert target_call["order"]["external_order_id"] == "ORD-GUL-99"

    # Phone simulator declines call without tenant header
    dec_res = await client.post(f"/api/v1/calls/{session_id}/decline")
    assert dec_res.status_code == 200
    assert dec_res.json()["status"] == "COMPLETED"


async def test_call_timeout_and_retry_schedule(client):
    reg_payload = {
        "store_name": "Junaid Jamshed Outlets",
        "admin_username": "jj_admin",
        "password": "password123",
        "default_language": "en",
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 200
    headers = {"X-Tenant-API-Key": reg_res.json()["api_key"]}

    order_payload = {
        "external_order_id": "ORD-JJ-101",
        "customer_name": "Ayesha Khan",
        "customer_phone": "+923211234567",
        "items_summary": "Festive Kurti",
        "cod_amount": 5400.0,
        "raw_address": "Street 4, Sector F-7/2, Islamabad",
        "payment_method": "COD",
    }
    ingest = await client.post("/api/v1/webhooks/orders", json=order_payload, headers=headers)
    assert ingest.status_code == 201
    order_id = ingest.json()["order"]["id"]

    # 1. Trigger call
    call1 = await client.post(f"/api/v1/calls/trigger-outbound/{order_id}", headers=headers)
    assert call1.status_code == 201
    sess1_id = call1.json()["session_id"]

    # 2. Customer does not answer -> Timeout after 25s
    timeout1 = await client.post(f"/api/v1/calls/{sess1_id}/timeout")
    assert timeout1.status_code == 200
    t1_data = timeout1.json()
    assert t1_data["order_status"] == "PENDING_RETRY"
    assert t1_data["call_attempts"] == 1
    assert t1_data["max_call_attempts"] == 3
    assert t1_data["next_retry_at"] is not None

    # 3. Fast-forward retry: Retry now
    retry1 = await client.post(f"/api/v1/calls/retry-order/{order_id}", headers=headers)
    assert retry1.status_code == 201
    sess2_id = retry1.json()["session_id"]
    assert sess2_id != sess1_id

    # 4. Second timeout
    timeout2 = await client.post(f"/api/v1/calls/{sess2_id}/timeout")
    assert timeout2.status_code == 200
    assert timeout2.json()["call_attempts"] == 2
    assert timeout2.json()["order_status"] == "PENDING_RETRY"

    # 5. Third call & timeout -> should transition to FAILED_CONTACT
    retry2 = await client.post(f"/api/v1/calls/retry-order/{order_id}", headers=headers)
    sess3_id = retry2.json()["session_id"]
    timeout3 = await client.post(f"/api/v1/calls/{sess3_id}/timeout")
    assert timeout3.status_code == 200
    t3_data = timeout3.json()
    assert t3_data["call_attempts"] == 3
    assert t3_data["order_status"] == "FAILED_CONTACT"
    assert t3_data["next_retry_at"] is None

    # 6. Test batch retry dispatcher
    order_payload2 = {
        "external_order_id": "ORD-JJ-102",
        "customer_name": "Hamza Tariq",
        "customer_phone": "+923335557788",
        "items_summary": "Men Shalwar Kameez",
        "cod_amount": 6200.0,
        "raw_address": "House 12, Street 3, G-11/3, Islamabad",
        "payment_method": "COD",
    }
    ingest2 = await client.post("/api/v1/webhooks/orders", json=order_payload2, headers=headers)
    o2_id = ingest2.json()["order"]["id"]
    call_o2 = await client.post(f"/api/v1/calls/trigger-outbound/{o2_id}", headers=headers)
    await client.post(f"/api/v1/calls/{call_o2.json()['session_id']}/timeout")

    # Dispatch retries with force=True
    dispatch = await client.post("/api/v1/calls/dispatch-retries?force=true", headers=headers)
    assert dispatch.status_code == 200
    d_data = dispatch.json()
    assert d_data["dispatched_count"] >= 1
    assert "ORD-JJ-102" in d_data["orders_retried"]




