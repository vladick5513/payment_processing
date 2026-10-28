from sqlalchemy import select

from app.dao.base import BaseDAO
from app.outbox.models import OutboxEvent


class OutboxDAO(BaseDAO[OutboxEvent]):
    model = OutboxEvent

    async def lock_unpublished(self, limit: int) -> list[OutboxEvent]:
        result = await self.session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result)
