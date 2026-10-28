import uuid

from app.database import session_factory
from app.enums import PaymentStatus
from app.gateway.client import PaymentGateway
from app.logger import logger
from app.payment.dao import PaymentDAO
from app.payment.schemas import PaymentRead
from app.webhook.client import WebhookClient


class PaymentProcessor:
    def __init__(self, gateway: PaymentGateway, webhooks: WebhookClient):
        self.gateway = gateway
        self.webhooks = webhooks

    async def process(self, payment_id: uuid.UUID) -> None:
        async with session_factory() as session:
            payment = await PaymentDAO(session).get_by_id(payment_id)
        if payment is None:
            logger.warning("Payment %s not found, skipping", payment_id)
            return

        if payment.status is PaymentStatus.PENDING:
            status = await self.gateway.charge(payment)
            async with session_factory() as session:
                dao = PaymentDAO(session)
                payment = await dao.finish(payment_id, status) or await dao.get_by_id(payment_id)
                await session.commit()
            assert payment is not None
            logger.info("Payment %s processed: %s", payment_id, payment.status)

        payload = PaymentRead.model_validate(payment).model_dump(mode="json")
        await self.webhooks.send(payment.webhook_url, payload)
        logger.info("Payment %s webhook delivered", payment_id)
