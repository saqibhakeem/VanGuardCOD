"""Async database engine, session factory, startup seed data, and helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.db.models import (
    ApprovalRequest,
    Base,
    CallDirection,
    CallSession,
    CallStatus,
    Order,
    OrderStatus,
    Tenant,
    utcnow,
)
from app.security import hash_api_key
from app.services.rto_scorer import assess_rto_risk

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_engine_url: str | None = None


def get_engine() -> AsyncEngine:
    global _engine, _engine_url
    url = get_settings().database_url
    if _engine is None or _engine_url != url:
        if url.startswith("sqlite"):
            _engine = create_async_engine(url, future=True, poolclass=NullPool)
        else:
            _engine = create_async_engine(url, future=True, pool_pre_ping=True)
        _engine_url = url
        if url.startswith("sqlite"):

            @event.listens_for(_engine.sync_engine, "connect")
            def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_database() -> None:
    global _engine, _session_factory, _engine_url
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
    _engine_url = None


async def init_db(*, seed: bool = True, reset: bool = False) -> None:
    engine = get_engine()
    if reset:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # Ensure new retry columns exist on orders table in SQLite
        try:
            from sqlalchemy import text
            res = await connection.execute(text("PRAGMA table_info(orders)"))
            cols = {row[1] for row in res.fetchall()}
            if cols:
                if "call_attempts" not in cols:
                    await connection.execute(text("ALTER TABLE orders ADD COLUMN call_attempts INTEGER NOT NULL DEFAULT 0"))
                if "max_call_attempts" not in cols:
                    await connection.execute(text("ALTER TABLE orders ADD COLUMN max_call_attempts INTEGER NOT NULL DEFAULT 3"))
                if "next_retry_at" not in cols:
                    await connection.execute(text("ALTER TABLE orders ADD COLUMN next_retry_at DATETIME"))
                if "last_call_at" not in cols:
                    await connection.execute(text("ALTER TABLE orders ADD COLUMN last_call_at DATETIME"))
        except Exception:
            pass

    if seed:
        factory = get_session_factory()
        async with factory() as session:
            await seed_database(session)


async def seed_database(session: AsyncSession) -> bool:
    """Create the default tenant and demo Karachi/Lahore orders when empty."""

    existing = await session.scalar(select(Tenant).limit(1))
    if existing is not None:
        return False

    settings = get_settings()
    tenant = Tenant(
        name="Karachi Threads & Textiles",
        api_key_hash=hash_api_key(settings.default_tenant_api_key),
        default_language="en",
        voice_persona=settings.tts_default_voice,
        max_auto_approve_cod=25000.0,
    )
    session.add(tenant)
    await session.flush()

    now = utcnow()
    demo_orders = [
        {
            "external_order_id": "ORD-9042",
            "customer_name": "Ayesha Khan",
            "customer_phone": "+923001234567",
            "items_summary": "2x Lawn Kurta (Medium), 1x Cotton Dupatta",
            "cod_amount": 12500.0,
            "raw_address": "House 42, Street 7, Block B, Gulshan-e-Iqbal, Karachi",
            "delivery_window": "Tomorrow 4 PM to 7 PM",
            "created_at": now - timedelta(minutes=48),
        },
        {
            "external_order_id": "ORD-9043",
            "customer_name": "Bilal Ahmed",
            "customer_phone": "+923214567890",
            "items_summary": "1x Formal Waistcoat (Large)",
            "cod_amount": 42000.0,
            "raw_address": "Flat 3C, Sea View Apartments, Clifton Block 5, Karachi",
            "delivery_window": None,
            "created_at": now - timedelta(minutes=31),
        },
        {
            "external_order_id": "ORD-9044",
            "customer_name": "Hina Raza",
            "customer_phone": "+924235678901",
            "items_summary": "3x Embroidered Chiffon Suit",
            "cod_amount": 8900.0,
            "raw_address": "Near Al-Falah Market, Lahore",
            "delivery_window": None,
            "created_at": now - timedelta(minutes=17),
        },
        {
            "external_order_id": "ORD-9045",
            "customer_name": "Usman Tariq",
            "customer_phone": "+923336789012",
            "items_summary": "1x Leather Jacket (XL), 2x Denim Jeans",
            "cod_amount": 31000.0,
            "raw_address": "DHA Phase 6, Lahore",
            "delivery_window": "Saturday morning",
            "created_at": now - timedelta(minutes=5),
        },
    ]

    for payload in demo_orders:
        assessment = assess_rto_risk(
            raw_address=payload["raw_address"],
            cod_amount=payload["cod_amount"],
            max_auto_approve_cod=tenant.max_auto_approve_cod,
        )
        session.add(
            Order(
                tenant_id=tenant.id,
                rto_risk_score=assessment.score,
                status=OrderStatus.PENDING_CALL,
                **payload,
            )
        )

    await session.commit()
    return True


def append_transcript(
    session: CallSession, role: str, text: str, *, timestamp_ms: int | None = None
) -> None:
    entry = {
        "role": role,
        "text": text,
        "timestamp_ms": timestamp_ms
        if timestamp_ms is not None
        else int(utcnow().timestamp() * 1000),
    }
    session.transcript = [*session.transcript, entry]


def append_tool_trace(session: CallSession, trace: dict[str, Any]) -> None:
    session.tool_traces = [*session.tool_traces, trace]
