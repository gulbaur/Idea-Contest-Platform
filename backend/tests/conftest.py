"""Общая тестовая инфраструктура (D-025).

- Тесты работают с настоящим PostgreSQL, но с отдельной БД `<имя>_test`.
- В начале прогона БД пересоздаётся и мигрирует Alembic — так проверяются и сами миграции.
- Перед каждым тестом все таблицы очищаются (TRUNCATE), а не откатываются:
  тестам конкурентности нужны настоящие коммиты из независимых соединений.
- Время управляется FakeClock (D-026).
"""

import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.clock import FakeClock
from app.config import Settings
from app.main import create_app
from app.models import Base, User
from app.seed import seed_demo_users
from tests.helpers import T0, TEST_PASSWORD

BACKEND_DIR = Path(__file__).resolve().parent.parent



def _test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    url = make_url(Settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


async def _recreate_database(database_url: str) -> None:
    url = make_url(database_url)
    if not url.database or not url.database.endswith("_test"):
        raise RuntimeError(f"Отказ пересоздавать БД без суффикса _test: {url.database!r}")
    admin = create_async_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    await admin.dispose()


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _test_database_url()
    asyncio.run(_recreate_database(url))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    return url


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(database_url=database_url, demo_password=TEST_PASSWORD, session_ttl_hours=24)


@pytest.fixture
async def app(settings: Settings, clock: FakeClock):
    application = create_app(settings=settings, clock=clock)
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with application.state.engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield application
    await application.state.engine.dispose()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def demo_users(app, clock: FakeClock) -> None:
    async with app.state.sessionmaker() as session:
        await seed_demo_users(session, TEST_PASSWORD, clock)


@pytest.fixture
async def user_ids(app, demo_users) -> dict[str, int]:
    """Логин демо-пользователя → id в БД."""
    async with app.state.sessionmaker() as session:
        rows = await session.execute(select(User.login, User.id))
        return dict(rows.all())
