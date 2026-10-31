"""Конкурсы, списки участников, идеи.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("submission_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("voting_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_request_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_contests"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_contests_created_by_users"),
        sa.UniqueConstraint(
            "created_by", "client_request_id", name="uq_contests_created_by_client_request_id"
        ),
        sa.CheckConstraint(
            "submission_deadline < voting_deadline", name="ck_contests_deadlines_ordered"
        ),
    )
    op.create_table(
        "contest_participants",
        sa.Column("contest_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("contest_id", "user_id", name="pk_contest_participants"),
        sa.ForeignKeyConstraint(
            ["contest_id"],
            ["contests.id"],
            name="fk_contest_participants_contest_id_contests",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_contest_participants_user_id_users"
        ),
    )
    op.create_index(
        "ix_contest_participants_user_id", "contest_participants", ["user_id"]
    )
    op.create_table(
        "ideas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contest_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("client_request_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ideas"),
        sa.ForeignKeyConstraint(
            ["contest_id"], ["contests.id"], name="fk_ideas_contest_id_contests", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name="fk_ideas_author_id_users"),
        sa.UniqueConstraint(
            "author_id", "client_request_id", name="uq_ideas_author_id_client_request_id"
        ),
    )
    op.create_index("ix_ideas_contest_order", "ideas", ["contest_id", "submitted_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_ideas_contest_order", table_name="ideas")
    op.drop_table("ideas")
    op.drop_index("ix_contest_participants_user_id", table_name="contest_participants")
    op.drop_table("contest_participants")
    op.drop_table("contests")
