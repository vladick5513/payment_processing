from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal

import asyncpg
import httpx
import pytest
from sqlalchemy import text

from app.database import Base, engine, session_factory
from app.enums import Currency
from app.main import app
from app.payment.models import Payment
from app.payment.schemas import PaymentCreate
from app.services.payment import PaymentService
from app.settings import settings


@pytest.fixture(scope="session", autouse=True)
async def database() -> AsyncIterator[None]:
    conn = await asyncpg.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASS,
        database="postgres",
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", settings.DB_NAME
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{settings.DB_NAME}"')
    finally:
        await conn.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    yield
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE payments, outbox"))


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": settings.API_KEY},
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def create_payment() -> Callable[..., Awaitable[Payment]]:
    async def _create(webhook_url: str = "http://example.com/hook", key: str = "key-1") -> Payment:
        data = PaymentCreate(
            amount=Decimal("100.50"),
            currency=Currency.RUB,
            description="Order 1",
            webhook_url=webhook_url,
        )
        async with session_factory() as session:
            payment = await PaymentService(session).create(data, key)
            await session.commit()
        return payment

    return _create
