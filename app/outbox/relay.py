import asyncio
from datetime import UTC, datetime

from faststream.rabbit import RabbitBroker

from app.broker import PAYMENTS_EXCHANGE
from app.database import session_factory
from app.logger import logger
from app.outbox.dao import OutboxDAO

BATCH_SIZE = 100
POLL_INTERVAL_SEC = 1.0


async def publish_batch(broker: RabbitBroker) -> int:
    async with session_factory() as session:
        events = await OutboxDAO(session).lock_unpublished(BATCH_SIZE)
        published = 0
        for event in events:
            try:
                await broker.publish(
                    event.payload,
                    exchange=PAYMENTS_EXCHANGE,
                    routing_key=event.event_type,
                    persist=True,
                    message_id=str(event.id),
                )
            except Exception:
                logger.exception("Outbox event %s publish failed", event.id)
                break
            event.published_at = datetime.now(UTC)
            published += 1
        await session.commit()
    return published


async def run_relay(broker: RabbitBroker) -> None:
    while True:
        try:
            published = await publish_batch(broker)
        except Exception:
            logger.exception("Outbox relay iteration failed")
            published = 0
        if published < BATCH_SIZE:
            await asyncio.sleep(POLL_INTERVAL_SEC)
