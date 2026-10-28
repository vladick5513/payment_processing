from typing import Any

from faststream.rabbit import RabbitBroker
from sqlalchemy import select

from app.database import session_factory
from app.outbox.models import OutboxEvent
from app.outbox.relay import publish_batch


class RecordingBroker(RabbitBroker):
    def __init__(self, fail: bool = False):
        super().__init__()
        self.fail = fail
        self.published: list[dict[str, Any]] = []

    async def publish(self, message: Any = None, *args: Any, **kwargs: Any) -> None:
        if self.fail:
            raise ConnectionError("broker is down")
        self.published.append({"message": message, **kwargs})


async def get_events() -> list[OutboxEvent]:
    async with session_factory() as session:
        return list(await session.scalars(select(OutboxEvent)))


async def test_publishes_pending_events_once(create_payment):
    payment = await create_payment()
    broker = RecordingBroker()

    assert await publish_batch(broker) == 1
    assert await publish_batch(broker) == 0

    assert len(broker.published) == 1
    sent = broker.published[0]
    assert sent["message"] == {"payment_id": str(payment.id)}
    assert sent["routing_key"] == "payment.created"
    assert sent["persist"] is True
    [event] = await get_events()
    assert event.published_at is not None


async def test_failed_publish_keeps_event_pending(create_payment):
    await create_payment()

    assert await publish_batch(RecordingBroker(fail=True)) == 0

    [event] = await get_events()
    assert event.published_at is None
