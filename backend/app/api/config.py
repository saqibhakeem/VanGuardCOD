"""Sanitized runtime configuration for the operational console."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import TenantDep
from app.config import get_settings
from app.schemas import RuntimeConfigOut, TenantOut

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=RuntimeConfigOut)
async def read_runtime_config(tenant: TenantDep) -> RuntimeConfigOut:
    settings = get_settings()
    return RuntimeConfigOut(
        tenant=TenantOut.model_validate(tenant),
        environment=settings.environment,
        api_prefix=settings.api_prefix,
        mock_mode=settings.mock_mode,
        stt_model=settings.stt_model,
        llm_model=settings.llm_model,
        fast_llm_model=settings.fast_llm_model,
        tts_model=settings.tts_model,
        tts_default_voice=settings.tts_default_voice,
        stt_language=settings.stt_language,
        llm_temperature=settings.llm_temperature,
        call_reconnect_grace_seconds=settings.call_reconnect_grace_seconds,
    )
