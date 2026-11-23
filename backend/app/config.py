"""Environment configuration for the VanguardCOD backend."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

MOCK_KEY_VALUES = {"", "test", "mock", "fake", "gsk_test", "none", "null"}

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./vanguard_cod.db"
DEFAULT_TENANT_API_KEY = "vcod_live_demo_key_2026"

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_PROJECT_DIR = _BACKEND_DIR.parent

for _dotenv_candidate in (_BACKEND_DIR / ".env", _PROJECT_DIR / ".env"):
    if _dotenv_candidate.is_file():
        load_dotenv(_dotenv_candidate, override=False)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = _env(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = _env(name)
    if value is None:
        return default
    return tuple(part.strip() for part in value.split(",") if part.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "VanguardCOD"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    environment: str = "development"
    database_url: str = DEFAULT_DATABASE_URL
    groq_api_key: str | None = None
    default_tenant_api_key: str = DEFAULT_TENANT_API_KEY
    stt_model: str = "whisper-large-v3-turbo"
    llm_model: str = "llama-3.3-70b-versatile"
    fast_llm_model: str = "llama-3.1-8b-instant"
    tts_model: str = "canopylabs/orpheus-v1-english"
    tts_default_voice: str = "troy"
    stt_language: str = "en"
    llm_temperature: float = 0.1
    seed_on_startup: bool = False
    allow_anonymous_tenant: bool = True
    call_reconnect_grace_seconds: float = 60.0
    cors_origins: tuple[str, ...] = field(default_factory=lambda: ("*",))

    @property
    def mock_mode(self) -> bool:
        key = (self.groq_api_key or "").strip().lower()
        return key in MOCK_KEY_VALUES or key.startswith("test_")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=_env("APP_NAME", "VanguardCOD") or "VanguardCOD",
            app_version=_env("APP_VERSION", "0.1.0") or "0.1.0",
            api_prefix=_env("API_PREFIX", "/api/v1") or "/api/v1",
            environment=_env("ENVIRONMENT", "development") or "development",
            database_url=_env("DATABASE_URL", DEFAULT_DATABASE_URL) or DEFAULT_DATABASE_URL,
            groq_api_key=_env("GROQ_API_KEY"),
            default_tenant_api_key=_env("DEFAULT_TENANT_API_KEY", DEFAULT_TENANT_API_KEY)
            or DEFAULT_TENANT_API_KEY,
            stt_model=_env("STT_MODEL", "whisper-large-v3-turbo") or "whisper-large-v3-turbo",
            llm_model=_env("LLM_MODEL", "llama-3.3-70b-versatile") or "llama-3.3-70b-versatile",
            fast_llm_model=_env("FAST_LLM_MODEL", "llama-3.1-8b-instant") or "llama-3.1-8b-instant",
            tts_model=_env("TTS_MODEL", "canopylabs/orpheus-v1-english")
            or "canopylabs/orpheus-v1-english",
            tts_default_voice=_env("TTS_DEFAULT_VOICE", "troy") or "troy",
            stt_language=_env("STT_LANGUAGE", "en") or "en",
            llm_temperature=float(_env("LLM_TEMPERATURE", "0.1") or "0.1"),
            seed_on_startup=_env_bool("SEED_ON_STARTUP", False),
            allow_anonymous_tenant=_env_bool("ALLOW_ANONYMOUS_TENANT", True),
            call_reconnect_grace_seconds=_env_float("CALL_RECONNECT_GRACE_SECONDS", 60.0),
            cors_origins=_env_list("CORS_ORIGINS", ("*",)),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
