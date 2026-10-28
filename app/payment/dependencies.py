import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.database import SessionDep
from app.payment.dao import PaymentDAO
from app.payment.models import Payment
from app.services.payment import PaymentService


async def get_payment_dao(session: SessionDep) -> PaymentDAO:
    return PaymentDAO(session)


PaymentDaoDep = Annotated[PaymentDAO, Depends(get_payment_dao)]


async def get_payment_service(session: SessionDep) -> PaymentService:
    return PaymentService(session)


PaymentServiceDep = Annotated[PaymentService, Depends(get_payment_service)]


async def valid_payment_id(payment_id: uuid.UUID, dao: PaymentDaoDep) -> Payment:
    payment = await dao.get_by_id(payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return payment


PaymentDep = Annotated[Payment, Depends(valid_payment_id)]

IdempotencyKeyHeader = Annotated[str, Header(min_length=1, max_length=255)]
