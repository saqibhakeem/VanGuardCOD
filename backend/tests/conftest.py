"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TEST_DB_PATH = Path(tempfile.gettempdir()) / f"vanguard_cod_test_{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["GROQ_API_KEY"] = "test"
os.environ["DEFAULT_TENANT_API_KEY"] = "vcod_live_demo_key_2026"
os.environ["ALLOW_ANONYMOUS_TENANT"] = "true"
os.environ["SEED_ON_STARTUP"] = "true"
os.environ["STT_LANGUAGE"] = "en"
os.environ["CALL_RECONNECT_GRACE_SECONDS"] = "30"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.models import CallDirection, CallSession, CallStatus, Order, Tenant
from app.db.session import get_session_factory, init_db
from app.main import app

TENANT_HEADERS = {"X-Tenant-API-Key": "vcod_live_demo_key_2026"}


@pytest_asyncio.fixture(autouse=True)
async def reset_database():
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except OSError:
            pass
    await init_db(seed=True, reset=True)
    yield


@pytest_asyncio.fixture
async def db():
    async with get_session_factory()() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest_asyncio.fixture
async def tenant(db) -> Tenant:
    result = await db.scalar(select(Tenant))
    assert result is not None
    return result


@pytest_asyncio.fixture
async def seeded_order(db, tenant) -> Order:
    order = await db.scalar(
        select(Order).where(
            Order.tenant_id == tenant.id,
            Order.external_order_id == "ORD-9042",
        )
    )
    assert order is not None
    return order


async def create_call_session(
    db,
    tenant: Tenant,
    order: Order,
    direction: str = CallDirection.OUTBOUND_VERIFY,
) -> CallSession:
    session = CallSession(
        tenant_id=tenant.id,
        order_id=order.id,
        direction=direction,
        status=CallStatus.ACTIVE,
        transcript=[],
        tool_traces=[],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session
