"""Сотрудники и доступ (D-062): роль администратора, отключение, вход по ссылке,
ограничение попыток входа, журнал действий.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_users_role_valid", "users", type_="check")
    op.create_check_constraint("role_valid", "users", "role IN ('admin', 'organizer', 'employee')")
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    # Приглашённый сотрудник ещё не задал пароль.
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)
    # Одноразовая ссылка для задания пароля: хранится только хеш (как у сессий, D-023).
    op.add_column("users", sa.Column("setup_token_hash", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("setup_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_users_setup_token_hash", "users", ["setup_token_hash"])
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    op.create_table(
        "login_throttle",
        sa.Column("login", sa.String(64), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("login", name="pk_login_throttle"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_audit_events_actor_id_users"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], name="fk_audit_events_target_user_id_users"),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("login_throttle")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_constraint("uq_users_setup_token_hash", "users", type_="unique")
    op.drop_column("users", "setup_expires_at")
    op.drop_column("users", "setup_token_hash")
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "is_active")
    op.drop_constraint("ck_users_role_valid", "users", type_="check")
    op.create_check_constraint("role_valid", "users", "role IN ('organizer', 'employee')")
