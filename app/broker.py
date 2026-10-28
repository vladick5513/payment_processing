from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.logger import logger
from app.settings import settings

broker = RabbitBroker(settings.RABBIT_URL, logger=logger)

PAYMENT_CREATED = "payment.created"

ATTEMPT_HEADER = "x-attempt"
RETRY_DELAYS_SEC = (2, 4)
MAX_ATTEMPTS = len(RETRY_DELAYS_SEC) + 1

PAYMENTS_EXCHANGE = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)
DEAD_LETTER_EXCHANGE = RabbitExchange("payments.dlx", type=ExchangeType.DIRECT, durable=True)

PROCESS_QUEUE = RabbitQueue(
    "payments.process",
    durable=True,
    routing_key=PAYMENT_CREATED,
    arguments={
        "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE.name,
        "x-dead-letter-routing-key": PAYMENT_CREATED,
    },
)

DEAD_LETTER_QUEUE = RabbitQueue("payments.process.dlq", durable=True, routing_key=PAYMENT_CREATED)

# Своя очередь на каждую задержку: per-message TTL в одной очереди истекает только с головы
RETRY_QUEUES = [
    RabbitQueue(
        f"payments.process.retry.{delay}s",
        durable=True,
        arguments={
            "x-message-ttl": delay * 1000,
            "x-dead-letter-exchange": PAYMENTS_EXCHANGE.name,
            "x-dead-letter-routing-key": PAYMENT_CREATED,
        },
    )
    for delay in RETRY_DELAYS_SEC
]


async def declare_topology() -> None:
    exchange = await broker.declare_exchange(PAYMENTS_EXCHANGE)
    dead_letter_exchange = await broker.declare_exchange(DEAD_LETTER_EXCHANGE)

    queue = await broker.declare_queue(PROCESS_QUEUE)
    await queue.bind(exchange, routing_key=PROCESS_QUEUE.routing())

    dead_letter_queue = await broker.declare_queue(DEAD_LETTER_QUEUE)
    await dead_letter_queue.bind(dead_letter_exchange, routing_key=DEAD_LETTER_QUEUE.routing())

    for retry_queue in RETRY_QUEUES:
        await broker.declare_queue(retry_queue)
