import asyncio
import uuid

from sqlalchemy import func, select

from app.database import session_factory
from app.outbox.models import OutboxEvent
from app.payment.models import Payment

PAYLOAD = {
    "amount": "1500.00",
    "currency": "RUB",
    "description": "Order 42",
    "metadata": {"order_id": 42},
    "webhook_url": "https://example.com/webhook",
}


async def count(model: type) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(model))


async def test_requires_api_key(client):
    response = await client.post(
        "/api/v1/payments",
        json=PAYLOAD,
        headers={"X-API-Key": "wrong", "Idempotency-Key": "k"},
    )
    assert response.status_code == 401


async def test_requires_idempotency_key(client):
    response = await client.post("/api/v1/payments", json=PAYLOAD)
    assert response.status_code == 422


async def test_rejects_unknown_currency(client):
    response = await client.post(
        "/api/v1/payments",
        json={**PAYLOAD, "currency": "GBP"},
        headers={"Idempotency-Key": "k"},
    )
    assert response.status_code == 422


async def test_create_writes_payment_and_outbox_event(client):
    response = await client.post("/api/v1/payments", json=PAYLOAD, headers={"Idempotency-Key": "k"})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert set(body) == {"payment_id", "status", "created_at"}
    async with session_factory() as session:
        event = await session.scalar(select(OutboxEvent))
    assert event.event_type == "payment.created"
    assert event.payload == {"payment_id": body["payment_id"]}
    assert event.published_at is None


async def test_repeat_with_same_key_returns_same_payment(client):
    headers = {"Idempotency-Key": "k"}
    first = await client.post("/api/v1/payments", json=PAYLOAD, headers=headers)
    second = await client.post("/api/v1/payments", json=PAYLOAD, headers=headers)

    assert first.json()["payment_id"] == second.json()["payment_id"]
    assert await count(Payment) == 1
    assert await count(OutboxEvent) == 1


async def test_concurrent_requests_with_same_key_create_one_payment(client):
    responses = await asyncio.gather(
        *(
            client.post("/api/v1/payments", json=PAYLOAD, headers={"Idempotency-Key": "k"})
            for _ in range(5)
        )
    )

    assert {r.status_code for r in responses} == {202}
    assert len({r.json()["payment_id"] for r in responses}) == 1
    assert await count(Payment) == 1
    assert await count(OutboxEvent) == 1


async def test_get_payment(client):
    created = await client.post("/api/v1/payments", json=PAYLOAD, headers={"Idempotency-Key": "k"})
    payment_id = created.json()["payment_id"]

    response = await client.get(f"/api/v1/payments/{payment_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["payment_id"] == payment_id
    assert body["amount"] == "1500.00"
    assert body["metadata"] == {"order_id": 42}
    assert body["idempotency_key"] == "k"
    assert body["processed_at"] is None


async def test_get_unknown_payment(client):
    response = await client.get(f"/api/v1/payments/{uuid.uuid4()}")
    assert response.status_code == 404
