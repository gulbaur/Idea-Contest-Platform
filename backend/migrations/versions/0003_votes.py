"""Голоса.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "votes",
        sa.Column("idea_id", sa.Integer(), nullable=False),
        sa.Column("voter_id", sa.Integer(), nullable=False),
        sa.Column("contest_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("idea_id", "voter_id", name="pk_votes"),
        sa.ForeignKeyConstraint(
            ["idea_id"], ["ideas.id"], name="fk_votes_idea_id_ideas", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["voter_id"], ["users.id"], name="fk_votes_voter_id_users"),
        sa.ForeignKeyConstraint(
            ["contest_id"], ["contests.id"], name="fk_votes_contest_id_contests", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_votes_contest_voter", "votes", ["contest_id", "voter_id"])


def downgrade() -> None:
    op.drop_index("ix_votes_contest_voter", table_name="votes")
    op.drop_table("votes")
