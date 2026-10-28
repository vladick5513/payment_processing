from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from aiohttp import web

from app.database import session_factory
from app.enums import PaymentStatus
from app.gateway.client import PaymentGateway
from app.payment.dao import PaymentDAO
from app.payment.models import Payment
from app.services.processing import PaymentProcessor
from app.webhook.client import WebhookClient
from app.webhook.exceptions import WebhookResponseError


class InstantGateway(PaymentGateway):
    def __init__(self, result: PaymentStatus):
        self.result = result
        self.calls = 0

    async def charge(self, payment: Payment) -> PaymentStatus:
        self.calls += 1
        return self.result


class WebhookReceiver:
    def __init__(self):
        self.received: list[dict[str, Any]] = []
        self.status = 200
        self.url = ""

    async def handle(self, request: web.Request) -> web.Response:
        self.received.append(await request.json())
        return web.Response(status=self.status)


@pytest.fixture
async def receiver() -> AsyncIterator[WebhookReceiver]:
    receiver = WebhookReceiver()
    server = web.Application()
    server.router.add_post("/hook", receiver.handle)
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    receiver.url = f"http://127.0.0.1:{port}/hook"
    yield receiver
    await runner.cleanup()


@pytest.fixture
async def webhooks() -> AsyncIterator[WebhookClient]:
    async with httpx.AsyncClient() as http:
        yield WebhookClient(http)


async def get_payment(payment_id) -> Payment:
    async with session_factory() as session:
        return await PaymentDAO(session).get_by_id(payment_id)


async def test_process_updates_status_and_sends_webhook(create_payment, receiver, webhooks):
    payment = await create_payment(webhook_url=receiver.url)
    processor = PaymentProcessor(InstantGateway(PaymentStatus.SUCCEEDED), webhooks)

    await processor.process(payment.id)

    stored = await get_payment(payment.id)
    assert stored.status is PaymentStatus.SUCCEEDED
    assert stored.processed_at is not None
    assert receiver.received[0]["payment_id"] == str(payment.id)
    assert receiver.received[0]["status"] == "succeeded"


async def test_failed_charge_is_reported(create_payment, receiver, webhooks):
    payment = await create_payment(webhook_url=receiver.url)
    processor = PaymentProcessor(InstantGateway(PaymentStatus.FAILED), webhooks)

    await processor.process(payment.id)

    assert (await get_payment(payment.id)).status is PaymentStatus.FAILED
    assert receiver.received[0]["status"] == "failed"


async def test_retry_after_webhook_error_does_not_charge_again(create_payment, receiver, webhooks):
    payment = await create_payment(webhook_url=receiver.url)
    gateway = InstantGateway(PaymentStatus.SUCCEEDED)
    processor = PaymentProcessor(gateway, webhooks)

    receiver.status = 500
    with pytest.raises(WebhookResponseError):
        await processor.process(payment.id)
    assert (await get_payment(payment.id)).status is PaymentStatus.SUCCEEDED

    receiver.status = 200
    await processor.process(payment.id)

    assert gateway.calls == 1
    assert len(receiver.received) == 2
