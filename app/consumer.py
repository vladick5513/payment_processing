import httpx
from faststream import AckPolicy, FastStream
from faststream.rabbit.annotations import RabbitMessage

from app.broker import (
    ATTEMPT_HEADER,
    MAX_ATTEMPTS,
    PAYMENTS_EXCHANGE,
    PROCESS_QUEUE,
    RETRY_DELAYS_SEC,
    RETRY_QUEUES,
    broker,
    declare_topology,
)
from app.gateway.client import PaymentGateway
from app.logger import logger
from app.payment.schemas import PaymentCreatedEvent
from app.services.processing import PaymentProcessor
from app.webhook.client import WebhookClient

http = httpx.AsyncClient(timeout=10)
processor = PaymentProcessor(PaymentGateway(), WebhookClient(http))

app = FastStream(broker)


@app.on_startup
async def setup_topology() -> None:
    await broker.connect()
    await declare_topology()


@app.after_shutdown
async def close_http() -> None:
    await http.aclose()


@broker.subscriber(PROCESS_QUEUE, PAYMENTS_EXCHANGE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def handle_payment_created(event: PaymentCreatedEvent, message: RabbitMessage) -> None:
    attempt = int(message.headers.get(ATTEMPT_HEADER, 1))
    try:
        await processor.process(event.payment_id)
    except Exception:
        if attempt >= MAX_ATTEMPTS:
            logger.exception(
                "Payment %s: attempt %s/%s failed, sending to DLQ",
                event.payment_id,
                attempt,
                MAX_ATTEMPTS,
            )
            raise
        logger.exception(
            "Payment %s: attempt %s/%s failed, retry in %ss",
            event.payment_id,
            attempt,
            MAX_ATTEMPTS,
            RETRY_DELAYS_SEC[attempt - 1],
        )
        await broker.publish(
            event,
            queue=RETRY_QUEUES[attempt - 1],
            headers={ATTEMPT_HEADER: attempt + 1},
            persist=True,
            message_id=message.message_id,
        )
