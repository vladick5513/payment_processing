from fastapi import APIRouter, status

from app.payment.dependencies import IdempotencyKeyHeader, PaymentDep, PaymentServiceDep
from app.payment.schemas import PaymentAccepted, PaymentCreate, PaymentRead

router = APIRouter(prefix="/api/v1/payments", tags=["Платежи"])


@router.post("", response_model=PaymentAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_payment(
    data: PaymentCreate,
    idempotency_key: IdempotencyKeyHeader,
    service: PaymentServiceDep,
):
    return await service.create(data, idempotency_key)


@router.get("/{payment_id}", response_model=PaymentRead)
async def get_payment(payment: PaymentDep):
    return payment
