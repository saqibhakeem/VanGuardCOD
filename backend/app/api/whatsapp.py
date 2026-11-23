"""WhatsApp webhook endpoints for Meta WhatsApp Cloud API and Twilio WhatsApp.

Handles:
- Meta Webhook Challenge Verification (GET /whatsapp/webhook)
- Meta Inbound Customer Messages (POST /whatsapp/webhook)
- Twilio Inbound WhatsApp Messages (POST /whatsapp/twilio-webhook)
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Form, HTTPException, Query, Request, Response, status

from app.config import get_settings
from app.services.whatsapp_agent import handle_whatsapp_incoming_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

DEFAULT_VERIFY_TOKEN = "vanguardcod_whatsapp_verify_token_2026"


@router.get("/webhook")
async def verify_meta_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
) -> Response:
    """Meta WhatsApp Webhook Verification Handshake."""
    logger.info("Meta Webhook Verification: mode=%s, token=%s", hub_mode, hub_verify_token)
    if hub_mode == "subscribe" and hub_challenge:
        # Accept verification token
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(content="Forbidden", status_code=status.HTTP_403_FORBIDDEN)


@router.post("/webhook")
async def receive_meta_whatsapp_message(request: Request) -> dict[str, str]:
    """Meta WhatsApp Cloud API Inbound Message Webhook."""
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return {"status": "ignored"}

    entries = body.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])
            for msg in messages:
                from_phone = msg.get("from")
                msg_type = msg.get("type")
                text_content = ""

                if msg_type == "text":
                    text_content = msg.get("text", {}).get("body", "").strip()
                elif msg_type == "button":
                    text_content = msg.get("button", {}).get("text", "").strip()
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    if interactive.get("type") == "button_reply":
                        text_content = interactive.get("button_reply", {}).get("title", "").strip()

                if from_phone and text_content:
                    await handle_whatsapp_incoming_message(
                        from_phone=from_phone,
                        message_text=text_content,
                        provider="META",
                    )

    return {"status": "ok"}


@router.post("/twilio-webhook")
async def receive_twilio_whatsapp_message(
    From: str = Form(default=""),
    Body: str = Form(default=""),
    MessageSid: str = Form(default=""),
) -> Response:
    """Twilio WhatsApp Inbound Message Webhook."""
    from_phone = From.replace("whatsapp:", "").strip()
    text_content = Body.strip()

    if from_phone and text_content:
        await handle_whatsapp_incoming_message(
            from_phone=from_phone,
            message_text=text_content,
            provider="TWILIO",
        )

    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?>\n<Response></Response>',
        media_type="application/xml",
    )
