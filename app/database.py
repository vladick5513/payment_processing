from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.settings import settings

engine = create_async_engine(
    settings.DATABASE_URL_asyncpg,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# scope="function": коммит до отправки ответа, а не после
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]
