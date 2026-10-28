from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base


class BaseDAO[ModelT: Base]:
    model: type[ModelT]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, **values: Any) -> ModelT:
        obj = self.model(**values)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get_by_id(self, obj_id: Any) -> ModelT | None:
        return await self.session.get(self.model, obj_id)
