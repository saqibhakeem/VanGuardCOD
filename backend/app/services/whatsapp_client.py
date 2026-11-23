"""Meta WhatsApp Cloud API client for outbound conversational messaging.

Interacts directly with Meta Graph API v19.0:
- Validates Phone Number ID and Access Token
- Sends conversational natural language messages to customer WhatsApp
- Handles message delivery receipts and mock fallbacks
"""

from __future__ import annotations

import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)

META_GRAPH_BASE = "https://graph.facebook.com/v19.0"


class WhatsAppError(Exception):
    def __init__(self, message: str, status_code: int = 400, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class WhatsAppClient:
    def __init__(self, phone_number_id: str, access_token: str, waba_id: str | None = None):
        self.phone_number_id = phone_number_id.strip()
        self.access_token = access_token.strip()
        self.waba_id = waba_id.strip() if waba_id else None

    @property
    def is_mock(self) -> bool:
        return (
            self.phone_number_id.lower().startswith("mock_")
            or self.access_token.lower().startswith("mock_")
            or self.phone_number_id.lower().startswith("test_")
            or "demo" in self.phone_number_id.lower()
        )

    async def validate_credentials(self) -> dict[str, Any]:
        """Validate Meta WhatsApp Phone Number ID and System Access Token."""
        if self.is_mock:
            return {
                "ok": True,
                "display_phone_number": "+92 300 0000000",
                "verified_name": "VanguardCOD Verified Store",
                "quality_rating": "GREEN",
                "error": None,
            }

        url = f"{META_GRAPH_BASE}/{self.phone_number_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    return {
                        "ok": True,
                        "display_phone_number": data.get("display_phone_number", "WhatsApp Connected"),
                        "verified_name": data.get("verified_name", "Registered Business"),
                        "quality_rating": data.get("quality_rating", "GREEN"),
                        "error": None,
                    }
                else:
                    data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                    err_obj = data.get("error", {})
                    msg = err_obj.get("message") or f"Meta HTTP {res.status_code}: {res.text[:120]}"
                    return {"ok": False, "error": msg}
        except Exception as exc:
            logger.warning("WhatsApp validation network error: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def send_text_message(
        self,
        recipient_phone: str,
        text_body: str,
    ) -> dict[str, Any]:
        """Send a natural language conversational message to customer WhatsApp."""
        # Normalize phone: Meta expects digits without '+' (e.g. 923001234567)
        clean_phone = recipient_phone.replace("+", "").replace("-", "").replace(" ", "").replace("whatsapp:", "")

        if self.is_mock:
            msg_id = f"wamid.mock_{abs(hash(clean_phone + text_body[:20])) % 1000000:06d}"
            logger.info("Mock WhatsApp message sent to %s (ID: %s): %s", clean_phone, msg_id, text_body[:70])
            return {
                "ok": True,
                "message_id": msg_id,
                "recipient": clean_phone,
            }

        url = f"{META_GRAPH_BASE}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": text_body,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code in (200, 201):
                    data = res.json()
                    messages = data.get("messages", [])
                    msg_id = messages[0].get("id") if messages else "sent"
                    return {
                        "ok": True,
                        "message_id": msg_id,
                        "recipient": clean_phone,
                    }
                else:
                    data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                    err_obj = data.get("error", {})
                    msg = err_obj.get("message") or f"Meta HTTP {res.status_code}: {res.text[:120]}"
                    raise WhatsAppError(f"Failed to send WhatsApp message: {msg}", status_code=res.status_code, details=data)
        except WhatsAppError:
            raise
        except Exception as exc:
            logger.error("WhatsApp message send exception: %s", exc)
            raise WhatsAppError(f"WhatsApp network error: {exc}")

    async def send_template_message(
        self,
        recipient_phone: str,
        template_name: str = "hello_world",
        language_code: str = "en_US",
    ) -> dict[str, Any]:
        """Send a pre-approved Meta WhatsApp Template message."""
        clean_phone = recipient_phone.replace("+", "").replace("-", "").replace(" ", "").replace("whatsapp:", "")
        if self.is_mock:
            return {"ok": True, "message_id": f"wamid.mock_tpl_{clean_phone}", "recipient": clean_phone}

        url = f"{META_GRAPH_BASE}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": clean_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code in (200, 201):
                    data = res.json()
                    messages = data.get("messages", [])
                    msg_id = messages[0].get("id") if messages else "sent"
                    return {"ok": True, "message_id": msg_id, "recipient": clean_phone}
                data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                err_obj = data.get("error", {})
                msg = err_obj.get("message") or f"Meta HTTP {res.status_code}: {res.text[:120]}"
                raise WhatsAppError(f"Failed to send template message: {msg}", status_code=res.status_code, details=data)
        except WhatsAppError:
            raise
        except Exception as exc:
            logger.error("WhatsApp template send exception: %s", exc)
            raise WhatsAppError(f"WhatsApp network error: {exc}")
