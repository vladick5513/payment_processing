from sqlalchemy.ext.asyncio import AsyncSession

from app.broker import PAYMENT_CREATED
from app.outbox.dao import OutboxDAO
from app.payment.dao import PaymentDAO
from app.payment.models import Payment
from app.payment.schemas import PaymentCreate, PaymentCreatedEvent


class PaymentService:
    def __init__(self, session: AsyncSession):
        self.payments = PaymentDAO(session)
        self.outbox = OutboxDAO(session)

    async def create(self, data: PaymentCreate, idempotency_key: str) -> Payment:
        payment = await self.payments.add_if_absent(
            idempotency_key=idempotency_key,
            amount=data.amount,
            currency=data.currency,
            description=data.description,
            meta=data.metadata,
            webhook_url=str(data.webhook_url),
        )
        if payment is None:
            existing = await self.payments.get_by_idempotency_key(idempotency_key)
            assert existing is not None
            return existing

        event = PaymentCreatedEvent(payment_id=payment.id)
        await self.outbox.add(event_type=PAYMENT_CREATED, payload=event.model_dump(mode="json"))
        return payment
