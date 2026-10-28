import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.dao.base import BaseDAO
from app.enums import PaymentStatus
from app.payment.models import Payment


class PaymentDAO(BaseDAO[Payment]):
    model = Payment

    async def add_if_absent(self, **values: Any) -> Payment | None:
        return await self.session.scalar(
            insert(Payment)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_payments_idempotency_key")
            .returning(Payment)
        )

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        return await self.session.scalar(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )

    async def finish(self, payment_id: uuid.UUID, status: PaymentStatus) -> Payment | None:
        return await self.session.scalar(
            update(Payment)
            .where(Payment.id == payment_id, Payment.status == PaymentStatus.PENDING)
            .values(status=status, processed_at=func.now())
            .returning(Payment)
        )
