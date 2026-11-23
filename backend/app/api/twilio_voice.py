"""Twilio Voice TwiML webhook handlers and bi-directional Media Stream WebSocket bridge.

Bridges real carrier phone calls directly into VanguardCOD's Groq Whisper + LLaMA 3.3 voice agent:
- Generates TwiML connecting Twilio call to Media Stream
- Ingests 8kHz mu-law audio over WebSocket, upsamples to 16kHz PCM16 for VAD & Whisper STT
- Transcodes TTS voice chunks (16kHz PCM16 -> 8kHz mu-law) and streams back to Twilio
- Handles barge-in by clearing Twilio media buffer upon customer speech
- Processes Twilio call status callbacks (busy, no-answer, completed)
"""

from __future__ import annotations

import asyncio
import audioop
import base64
import json
import logging
from typing import Any
from fastapi import APIRouter, Form, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.agents.outbound_verifier import build_outbound_agent
from app.config import get_settings
from app.db.models import CallDirection, CallSession, CallStatus, Order, OrderStatus, Tenant, utcnow
from app.db.session import get_session_factory
from app.voice.session import AudioSessionController

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/twilio/voice", tags=["twilio-voice"])


def _twiml_response(xml_content: str) -> Response:
    return Response(
        content=f'<?xml version="1.0" encoding="UTF-8"?>\n<Response>\n{xml_content}\n</Response>',
        media_type="application/xml",
    )


@router.post("/{session_id}/twiml")
async def get_twiml_stream(
    session_id: str,
    request: Request,
) -> Response:
    """Return TwiML instruction to connect the inbound/outbound call to the Media Stream."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "127.0.0.1:8100"
    scheme = "wss" if request.headers.get("x-forwarded-proto") == "https" else "ws"
    stream_url = f"{scheme}://{host}/api/v1/twilio/voice/stream/{session_id}"

    # Connect to bi-directional media stream
    xml = (
        f'  <Connect>\n'
        f'    <Stream url="{stream_url}">\n'
        f'      <Parameter name="sessionId" value="{session_id}" />\n'
        f'    </Stream>\n'
        f'  </Connect>'
    )
    return _twiml_response(xml)


@router.post("/{session_id}/status")
async def handle_call_status(
    session_id: str,
    CallSid: str = Form(default=""),
    CallStatusParam: str = Form(default="", alias="CallStatus"),
    CallDuration: str = Form(default="0"),
) -> Response:
    """Handle Twilio call status callback (ringing, in-progress, completed, busy, no-answer)."""
    logger.info("Twilio status callback for session %s: SID=%s, Status=%s, Duration=%s", session_id, CallSid, CallStatusParam, CallDuration)

    async with get_session_factory()() as db:
        session = await db.scalar(select(CallSession).where(CallSession.id == session_id))
        if session is not None:
            session.provider_call_sid = CallSid or session.provider_call_sid
            order = await db.scalar(select(Order).where(Order.id == session.order_id))

            if CallStatusParam.lower() in ("no-answer", "busy", "failed", "canceled"):
                session.status = CallStatus.FAILED
                if order is not None:
                    order.status = OrderStatus.PENDING_RETRY
                    order.call_attempts = (order.call_attempts or 0) + 1
                    order.last_call_at = utcnow()
                    # Schedule retry in 2 hours
                    from datetime import timedelta
                    order.next_retry_at = utcnow() + timedelta(hours=2)

                    # Check if tenant has WhatsApp enabled for instant omnichannel fallback
                    tenant = await db.scalar(select(Tenant).where(Tenant.id == session.tenant_id))
                    if tenant and tenant.channel_choice in ("WHATSAPP", "BOTH"):
                        try:
                            from app.services.omnichannel import dispatch_whatsapp_verification
                            asyncio.create_task(dispatch_whatsapp_verification(order.id, tenant.id))
                            logger.info("Dispatched WhatsApp omnichannel fallback for order %s after call %s", order.id, CallStatusParam)
                        except Exception as exc:
                            logger.warning("Failed to dispatch WhatsApp fallback: %s", exc)

            elif CallStatusParam.lower() == "completed":
                if session.status == CallStatus.ACTIVE:
                    session.status = CallStatus.COMPLETED

            await db.commit()

    return Response(content="<Response/>", media_type="application/xml")


@router.websocket("/stream/{session_id}")
async def twilio_media_stream_websocket(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """Bi-directional Twilio Media Stream WebSocket connecting customer telephony to Voice Agent."""
    await websocket.accept()

    async with get_session_factory()() as db:
        call_session = await db.scalar(select(CallSession).where(CallSession.id == session_id))
        if not call_session:
            await websocket.close(code=4404)
            return

        order = await db.scalar(select(Order).where(Order.id == call_session.order_id))
        tenant = await db.scalar(select(Tenant).where(Tenant.id == call_session.tenant_id))
        if not order or not tenant:
            await websocket.close(code=4404)
            return

        agent = build_outbound_agent(tenant=tenant, order=order)

    # Initialize Voice Session Controller
    controller = AudioSessionController(
        session_id=session_id,
        tenant_id=tenant.id,
        order_id=order.id,
        direction=call_session.direction,
        agent=agent,
        voice=tenant.voice_persona or get_settings().tts_default_voice,
    )

    stream_sid: str | None = None
    rate_state: tuple[Any, ...] | None = None

    # Forward assistant voice chunks to Twilio
    async def _send_audio_to_twilio() -> None:
        nonlocal stream_sid, rate_state
        try:
            while True:
                # Wait for synthesized PCM16 16kHz audio from TTS provider
                chunk_16k = await controller.tts_queue.get()
                if not chunk_16k:
                    continue

                if not stream_sid:
                    await asyncio.sleep(0.05)
                    continue

                # Downsample 16kHz PCM16 -> 8kHz PCM16, then convert to 8kHz mu-law
                try:
                    chunk_8k, rate_state = audioop.ratecv(chunk_16k, 2, 1, 16000, 8000, rate_state)
                    mulaw_8k = audioop.lin2ulaw(chunk_8k, 2)
                    payload_b64 = base64.b64encode(mulaw_8k).decode("ascii")

                    # Send media event to Twilio
                    msg = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": payload_b64},
                    }
                    await websocket.send_text(json.dumps(msg))
                except Exception as trans_err:
                    logger.warning("Audio transcode error: %s", trans_err)
        except (asyncio.CancelledError, WebSocketDisconnect):
            pass

    audio_task = asyncio.create_task(_send_audio_to_twilio(), name=f"twilio-out-{session_id}")

    try:
        # Start the controller background loops (speech synthesis & processing)
        await controller.start()

        # Ingest incoming audio events from Twilio
        while True:
            raw_text = await websocket.receive_text()
            data = json.loads(raw_text)
            event_type = data.get("event")

            if event_type == "start":
                start_data = data.get("start", {})
                stream_sid = data.get("streamSid") or start_data.get("streamSid")
                call_sid = start_data.get("callSid")
                logger.info("Twilio Stream START: session=%s, streamSid=%s, callSid=%s", session_id, stream_sid, call_sid)

                # Update call session with provider call sid
                async with get_session_factory()() as db:
                    s = await db.scalar(select(CallSession).where(CallSession.id == session_id))
                    if s:
                        s.provider_call_sid = call_sid
                        await db.commit()

            elif event_type == "media":
                media_payload = data.get("media", {}).get("payload")
                if not media_payload:
                    continue

                # Decode base64 8kHz mu-law audio
                mulaw_bytes = base64.b64decode(media_payload)

                # Convert 8kHz mu-law -> 8kHz linear PCM16, then upsample to 16kHz PCM16
                pcm_8k = audioop.ulaw2lin(mulaw_bytes, 2)
                pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)

                # Feed audio to VAD and speech recognition
                await controller.ingest_audio(pcm_16k)

                # If customer barged in, tell Twilio to clear its outbound buffer
                if controller.interrupted:
                    if stream_sid:
                        await websocket.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))

            elif event_type == "stop":
                logger.info("Twilio Stream STOP for session %s", session_id)
                break

    except WebSocketDisconnect:
        logger.info("Twilio WebSocket disconnected for session %s", session_id)
    except Exception as exc:
        logger.warning("Twilio stream exception for session %s: %s", session_id, exc)
    finally:
        audio_task.cancel()
        await controller.stop()
