import asyncio
import random

from app.enums import PaymentStatus
from app.payment.models import Payment


class PaymentGateway:
    async def charge(self, payment: Payment) -> PaymentStatus:
        await asyncio.sleep(random.uniform(2, 5))
        if random.random() < 0.9:
            return PaymentStatus.SUCCEEDED
        return PaymentStatus.FAILED
