"""Настройки вида у пользователя: тема, шрифт, язык (D-060).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default заполняет и уже существующих пользователей.
    op.add_column("users", sa.Column("theme", sa.String(16), nullable=False, server_default="system"))
    op.add_column("users", sa.Column("font", sa.String(16), nullable=False, server_default="inter"))
    op.add_column("users", sa.Column("locale", sa.String(8), nullable=False, server_default="ru"))
    op.create_check_constraint("theme_valid", "users", "theme IN ('system', 'light', 'dark')")
    op.create_check_constraint("font_valid", "users", "font IN ('inter', 'plex', 'golos', 'system')")
    op.create_check_constraint("locale_valid", "users", "locale IN ('ru', 'en')")


def downgrade() -> None:
    op.drop_constraint("ck_users_locale_valid", "users", type_="check")
    op.drop_constraint("ck_users_font_valid", "users", type_="check")
    op.drop_constraint("ck_users_theme_valid", "users", type_="check")
    op.drop_column("users", "locale")
    op.drop_column("users", "font")
    op.drop_column("users", "theme")
