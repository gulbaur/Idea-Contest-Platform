"""Схема после миграций Alembic совпадает с моделями SQLAlchemy (D-021)."""

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from app.models import Base


async def test_migrations_match_models(app):
    def diff(sync_connection):
        return compare_metadata(MigrationContext.configure(sync_connection), Base.metadata)

    async with app.state.engine.connect() as conn:
        differences = await conn.run_sync(diff)

    assert differences == []
