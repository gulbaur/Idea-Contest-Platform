"""Подключение к PostgreSQL через SQLAlchemy (async) и asyncpg (D-020)."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str) -> AsyncEngine:
    # Соединения открываются лениво — при первом запросе, а не здесь.
    return create_async_engine(database_url, pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: после commit объекты можно читать без нового запроса к БД.
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Зависимость FastAPI: одна сессия БД на один HTTP-запрос.

    Транзакцию открывает первый запрос к БД; фиксирует её обработчик
    явным `await db.commit()`. Если обработчик завершился без commit
    (в том числе из-за ошибки), изменения откатываются при закрытии сессии.
    """
    async with request.app.state.sessionmaker() as session:
        yield session
