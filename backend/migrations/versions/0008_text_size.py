"""Размер текста интерфейса в настройках пользователя (D-066).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("text_size", sa.String(8), nullable=False, server_default="medium"))
    op.create_check_constraint("text_size_valid", "users", "text_size IN ('small', 'medium', 'large')")


def downgrade() -> None:
    op.drop_constraint("ck_users_text_size_valid", "users", type_="check")
    op.drop_column("users", "text_size")
