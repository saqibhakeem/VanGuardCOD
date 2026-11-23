"""Unit and integration tests for WhatsApp Conversational Agent, Twilio Voice, and Omnichannel routing."""

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.db.models import OrderStatus

TENANT_HEADERS = {"X-Tenant-API-Key": "vcod_live_demo_key_2026"}


@pytest.mark.asyncio
async def test_store_registration_with_channel_choice(client: AsyncClient):
    """Verify new store can register and select communication channel with credentials."""
    payload = {
        "store_name": "Sapphire Retail",
        "admin_username": "sapphire_admin",
        "password": "password123",
        "channel_choice": "BOTH",
        "twilio_account_sid": "mock_AC1234567890",
        "twilio_auth_token": "mock_auth_token_secret",
        "twilio_from_number": "+12025550199",
        "whatsapp_provider": "META",
        "whatsapp_phone_number_id": "mock_phone_id_9988",
        "whatsapp_access_token": "mock_wa_access_token",
        "whatsapp_waba_id": "mock_waba_123",
        "omnichannel_strategy": "WHATSAPP_FIRST",
    }
    res = await client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    tenant = data["tenant"]
    assert tenant["name"] == "Sapphire Retail"
    assert tenant["channel_choice"] == "BOTH"
    assert tenant["twilio_account_sid"] == "mock_AC1234567890"
    assert tenant["whatsapp_provider"] == "META"
    assert tenant["has_twilio_auth_token"] is True
    assert tenant["has_whatsapp_access_token"] is True


@pytest.mark.asyncio
async def test_channel_config_endpoints(client: AsyncClient):
    """Verify channels config can be inspected and updated."""
    # 1. Get channel config
    res = await client.get("/api/v1/channels/config", headers=TENANT_HEADERS)
    assert res.status_code == 200
    cfg = res.json()
    assert "channel_choice" in cfg
    assert "omnichannel_strategy" in cfg

    # 2. Update channel config
    update_payload = {
        "channel_choice": "WHATSAPP",
        "whatsapp_provider": "META",
        "whatsapp_phone_number_id": "mock_pid_555",
        "whatsapp_access_token": "mock_token_abc",
        "omnichannel_strategy": "WHATSAPP_FIRST",
    }
    update_res = await client.put(
        "/api/v1/channels/config", json=update_payload, headers=TENANT_HEADERS
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["channel_choice"] == "WHATSAPP"
    assert updated["whatsapp_phone_number_id"] == "mock_pid_555"
    assert updated["has_whatsapp_access_token"] is True


@pytest.mark.asyncio
async def test_provider_credential_validation(client: AsyncClient):
    """Verify in-app test connection endpoints for Twilio and WhatsApp."""
    # Test Twilio validation
    tw_res = await client.post(
        "/api/v1/channels/test-twilio",
        json={"account_sid": "mock_AC_test_account", "auth_token": "mock_secret_key"},
        headers=TENANT_HEADERS,
    )
    assert tw_res.status_code == 200
    assert tw_res.json()["ok"] is True

    # Test WhatsApp validation
    wa_res = await client.post(
        "/api/v1/channels/test-whatsapp",
        json={
            "provider": "META",
            "phone_number_id": "mock_phone_999",
            "access_token": "mock_token_xyz",
        },
        headers=TENANT_HEADERS,
    )
    assert wa_res.status_code == 200
    assert wa_res.json()["ok"] is True


@pytest.mark.asyncio
async def test_meta_whatsapp_webhook_handshake(client: AsyncClient):
    """Verify Meta Webhook verification challenge responds with challenge string."""
    res = await client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "123456789_challenge_nonce",
            "hub.verify_token": "vanguardcod_whatsapp_verify_token_2026",
        },
    )
    assert res.status_code == 200
    assert res.text == "123456789_challenge_nonce"


@pytest.mark.asyncio
async def test_whatsapp_conversational_chat_agent(client: AsyncClient):
    """Verify WhatsApp multi-turn conversational agent processes customer text and confirms order."""
    # Ingest a new test order
    order_payload = {
        "external_order_id": "ORD-WA-TEST-1",
        "customer_name": "Ayesha Khan",
        "customer_phone": "+923001122334",
        "items_summary": "Silk Embroidered Shawl x 1",
        "cod_amount": 6200.0,
        "raw_address": "House 12, Street 3, Gulberg III, Lahore",
        "payment_method": "COD",
    }
    ingest = await client.post(
        "/api/v1/webhooks/orders", json=order_payload, headers=TENANT_HEADERS
    )
    assert ingest.status_code == 201
    order_id = ingest.json()["order"]["id"]

    # Trigger outbound verification specifically on WhatsApp
    trig = await client.post(
        f"/api/v1/calls/trigger-outbound/{order_id}?channel=WHATSAPP",
        headers=TENANT_HEADERS,
    )
    assert trig.status_code == 201
    session_id = trig.json()["session_id"]
    assert trig.json()["channel"] == "WHATSAPP"

    # Simulate customer replying on WhatsApp: "Yes, I confirm my order. Landmark is opposite Al-Fatah Mall"
    meta_webhook_body = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "923001122334",
                                    "type": "text",
                                    "text": {
                                        "body": "Yes, I confirm this order! Delivery landmark is opposite Al-Fatah Mall, Main Market."
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    res = await client.post("/api/v1/whatsapp/webhook", json=meta_webhook_body)
    assert res.status_code == 200

    # Verify order was confirmed and landmark updated
    check = await client.get(
        "/api/v1/orders",
        params={"external_order_id": "ORD-WA-TEST-1"},
        headers=TENANT_HEADERS,
    )
    assert check.status_code == 200
    orders = check.json()
    assert len(orders) >= 1
    verified_order = orders[0]
    assert verified_order["status"] == OrderStatus.VERIFIED
    assert bool(verified_order["verified_landmark"])


@pytest.mark.asyncio
async def test_twilio_voice_twiml_generation(client: AsyncClient):
    """Verify Twilio voice TwiML endpoint generates valid stream XML."""
    listing = await client.get(
        "/api/v1/orders",
        params={"external_order_id": "ORD-9042"},
        headers=TENANT_HEADERS,
    )
    order_id = listing.json()[0]["id"]
    trigger = await client.post(
        f"/api/v1/calls/trigger-outbound/{order_id}", headers=TENANT_HEADERS
    )
    session_id = trigger.json()["session_id"]

    res = await client.post(f"/api/v1/twilio/voice/{session_id}/twiml")
    assert res.status_code == 200
    assert "application/xml" in res.headers.get("content-type", "")
    assert "<Stream" in res.text
    assert f"twilio/voice/stream/{session_id}" in res.text


@pytest.mark.asyncio
async def test_twilio_call_status_no_answer_retry(client: AsyncClient):
    """Verify Twilio 'no-answer' status callback schedules 2-hour retry."""
    listing = await client.get(
        "/api/v1/orders",
        params={"external_order_id": "ORD-9042"},
        headers=TENANT_HEADERS,
    )
    order_id = listing.json()[0]["id"]
    trigger = await client.post(
        f"/api/v1/calls/trigger-outbound/{order_id}", headers=TENANT_HEADERS
    )
    session_id = trigger.json()["session_id"]

    # Twilio reports no-answer
    res = await client.post(
        f"/api/v1/twilio/voice/{session_id}/status",
        data={
            "CallSid": "CA_test_123",
            "CallStatus": "no-answer",
            "CallDuration": "25",
        },
    )
    assert res.status_code == 200

    # Order should now be PENDING_RETRY with next_retry_at scheduled
    check = await client.get(
        "/api/v1/orders",
        params={"external_order_id": "ORD-9042"},
        headers=TENANT_HEADERS,
    )
    order = check.json()[0]
    assert order["status"] == OrderStatus.PENDING_RETRY
    assert order["next_retry_at"] is not None
    assert order["call_attempts"] >= 1
