import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI

from app.broker import broker, declare_topology
from app.outbox.relay import run_relay
from app.payment.router import router as payment_router
from app.security import verify_api_key


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await broker.connect()
    await declare_topology()
    relay = asyncio.create_task(run_relay(broker))
    try:
        yield
    finally:
        relay.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await relay
        await broker.stop()


app = FastAPI(
    title="payment-processing",
    lifespan=lifespan,
    dependencies=[Depends(verify_api_key)],
)

for r in (payment_router,):
    app.include_router(r)
