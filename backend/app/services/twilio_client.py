"""Twilio REST API client for outbound voice calls and WhatsApp messaging.

Supports:
- Credential validation against Twilio Accounts API
- Outbound voice call dispatching with TwiML webhook URL and 25s timeout
- Outbound WhatsApp messaging via Twilio WhatsApp Sender
- Mock mode fallback for local testing and CI/CD
"""

from __future__ import annotations

import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


class TwilioError(Exception):
    def __init__(self, message: str, status_code: int = 400, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class TwilioClient:
    def __init__(self, account_sid: str, auth_token: str, default_from: str | None = None):
        self.account_sid = account_sid.strip()
        self.auth_token = auth_token.strip()
        self.default_from = default_from.strip() if default_from else None

    @property
    def is_mock(self) -> bool:
        return (
            self.account_sid.lower().startswith("mock_")
            or self.account_sid.lower().startswith("test_")
            or "demo" in self.account_sid.lower()
        )

    async def validate_credentials(self) -> dict[str, Any]:
        """Validate Account SID and Auth Token against Twilio Accounts endpoint."""
        if self.is_mock:
            return {
                "ok": True,
                "friendly_name": f"Mock Twilio Account ({self.account_sid})",
                "account_status": "active",
                "error": None,
            }

        url = f"{TWILIO_API_BASE}/Accounts/{self.account_sid}.json"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, auth=(self.account_sid, self.auth_token))
                if res.status_code == 200:
                    data = res.json()
                    return {
                        "ok": True,
                        "friendly_name": data.get("friendly_name", "Twilio Account"),
                        "account_status": data.get("status", "active"),
                        "error": None,
                    }
                else:
                    data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                    err_msg = data.get("message") or f"Twilio HTTP {res.status_code}: {res.text[:120]}"
                    return {"ok": False, "error": err_msg}
        except Exception as exc:
            logger.warning("Twilio validation network error: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def initiate_voice_call(
        self,
        to_phone: str,
        twiml_url: str,
        from_phone: str | None = None,
        status_callback_url: str | None = None,
        timeout_seconds: int = 25,
    ) -> dict[str, Any]:
        """Initiate outbound phone call to customer with TwiML URL and 25s ring timeout."""
        caller_id = from_phone or self.default_from
        if not caller_id and not self.is_mock:
            raise TwilioError("Twilio 'From' phone number is required to place outbound calls.")

        if self.is_mock:
            call_sid = f"CA_mock_{abs(hash(to_phone + twiml_url)) % 1000000:06d}"
            logger.info("Mock Twilio call placed to %s (SID: %s, URL: %s)", to_phone, call_sid, twiml_url)
            return {
                "call_sid": call_sid,
                "status": "queued",
                "to": to_phone,
                "from": caller_id or "+15005550006",
            }

        url = f"{TWILIO_API_BASE}/Accounts/{self.account_sid}/Calls.json"
        form_data: dict[str, Any] = {
            "To": to_phone,
            "From": caller_id,
            "Url": twiml_url,
            "Timeout": str(timeout_seconds),
        }
        if status_callback_url:
            form_data["StatusCallback"] = status_callback_url
            form_data["StatusCallbackEvent"] = ["initiated", "ringing", "answered", "completed"]

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.post(url, data=form_data, auth=(self.account_sid, self.auth_token))
                if res.status_code in (200, 201):
                    data = res.json()
                    return {
                        "call_sid": data.get("sid"),
                        "status": data.get("status", "queued"),
                        "to": data.get("to"),
                        "from": data.get("from"),
                    }
                else:
                    data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                    msg = data.get("message") or f"Twilio HTTP {res.status_code}: {res.text[:120]}"
                    raise TwilioError(f"Failed to place Twilio call: {msg}", status_code=res.status_code, details=data)
        except TwilioError:
            raise
        except Exception as exc:
            logger.error("Twilio call exception: %s", exc)
            raise TwilioError(f"Twilio connection error: {exc}")

    async def send_whatsapp_message(
        self,
        to_phone: str,
        body: str,
        from_phone: str | None = None,
        status_callback_url: str | None = None,
    ) -> dict[str, Any]:
        """Send WhatsApp message using Twilio WhatsApp Sender."""
        caller_id = from_phone or self.default_from
        if not caller_id and not self.is_mock:
            raise TwilioError("Twilio 'From' WhatsApp number is required.")

        to_formatted = to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}"
        from_formatted = caller_id if caller_id and caller_id.startswith("whatsapp:") else f"whatsapp:{caller_id}"

        if self.is_mock:
            msg_sid = f"SM_mock_{abs(hash(to_phone + body[:20])) % 1000000:06d}"
            logger.info("Mock Twilio WhatsApp message sent to %s (SID: %s): %s", to_formatted, msg_sid, body[:60])
            return {
                "message_sid": msg_sid,
                "status": "queued",
                "to": to_formatted,
                "from": from_formatted,
            }

        url = f"{TWILIO_API_BASE}/Accounts/{self.account_sid}/Messages.json"
        form_data: dict[str, Any] = {
            "To": to_formatted,
            "From": from_formatted,
            "Body": body,
        }
        if status_callback_url:
            form_data["StatusCallback"] = status_callback_url

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.post(url, data=form_data, auth=(self.account_sid, self.auth_token))
                if res.status_code in (200, 201):
                    data = res.json()
                    return {
                        "message_sid": data.get("sid"),
                        "status": data.get("status", "queued"),
                        "to": data.get("to"),
                        "from": data.get("from"),
                    }
                else:
                    data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                    msg = data.get("message") or f"Twilio HTTP {res.status_code}: {res.text[:120]}"
                    raise TwilioError(f"Failed to send Twilio WhatsApp: {msg}", status_code=res.status_code, details=data)
        except TwilioError:
            raise
        except Exception as exc:
            logger.error("Twilio WhatsApp exception: %s", exc)
            raise TwilioError(f"Twilio WhatsApp connection error: {exc}")
