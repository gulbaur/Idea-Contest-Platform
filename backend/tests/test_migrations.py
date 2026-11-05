"""Схема после миграций Alembic совпадает с моделями SQLAlchemy (D-021)."""

import asyncio

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.models import Base
from tests.conftest import BACKEND_DIR, _recreate_database


async def test_migrations_match_models(app):
    def diff(sync_connection):
        return compare_metadata(MigrationContext.configure(sync_connection), Base.metadata)

    async with app.state.engine.connect() as conn:
        differences = await conn.run_sync(diff)

    assert differences == []


def test_migration_0004_plans_jobs_for_contests_created_before_it(database_url):
    """Конкурсы, созданные до этапа 5, получают задания (D-042).

    Отдельная временная БД: схема до 0003 → конкурсы → миграция до 0004.
    """
    url = make_url(database_url).set(database=f"{make_url(database_url).database}_backfill_test")
    url_text = url.render_as_string(hide_password=False)
    asyncio.run(_recreate_database(url_text))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = url_text
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0003")

    async def seed() -> None:
        engine = create_async_engine(url_text, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO users (id, login, display_name, email, role, password_hash, created_at) "
                "VALUES (1, 'organizer', 'Организатор', 'o@example.com', 'organizer', 'x', now())"
            ))
            # Конкурс 1: раунды по 3 суток; конкурс 2: раунды по 1 часу (короче суток).
            await conn.execute(text(
                "INSERT INTO contests (id, topic, submission_deadline, voting_deadline, created_by, "
                "created_at, client_request_id, revision) VALUES "
                "(1, 'Длинный', '2026-01-04T00:00Z', '2026-01-07T00:00Z', 1, '2026-01-01T00:00Z', "
                "gen_random_uuid(), 1), "
                "(2, 'Короткий', '2026-01-01T01:00Z', '2026-01-01T02:00Z', 1, '2026-01-01T00:00Z', "
                "gen_random_uuid(), 1)"
            ))
        await engine.dispose()

    async def jobs() -> list[tuple]:
        engine = create_async_engine(url_text, poolclass=NullPool)
        async with engine.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT contest_id, kind, to_char(run_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI'), "
                "status, note, finished_at IS NOT NULL FROM jobs ORDER BY contest_id, kind"
            ))).all()
        await engine.dispose()
        return [tuple(r) for r in rows]

    asyncio.run(seed())
    command.upgrade(cfg, "0004")

    assert asyncio.run(jobs()) == [
        (1, "finalize", "2026-01-07 00:00", "pending", None, False),
        (1, "remind_submission", "2026-01-03 00:00", "pending", None, False),
        (1, "remind_voting", "2026-01-06 00:00", "pending", None, False),
        (2, "finalize", "2026-01-01 02:00", "pending", None, False),
        (2, "remind_submission", "2025-12-31 01:00", "skipped", "раунд короче срока напоминания", True),
        (2, "remind_voting", "2025-12-31 02:00", "skipped", "раунд короче срока напоминания", True),
    ]

    # 0007 (D-063): уже созданным конкурсам — задание «голосование открыто». Эти конкурсы в прошлом,
    # приём идей давно закончился — задание сразу пропущено, письма задним числом не уходят.
    command.upgrade(cfg, "head")
    opened = [row for row in asyncio.run(jobs()) if row[1] == "open_voting"]
    assert opened == [
        (1, "open_voting", "2026-01-04 00:00", "skipped", "конкурс создан до появления этого письма", True),
        (2, "open_voting", "2026-01-01 01:00", "skipped", "конкурс создан до появления этого письма", True),
    ]
