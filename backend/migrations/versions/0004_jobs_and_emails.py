"""Задания расписания и письма почтовой заглушки.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contest_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.ForeignKeyConstraint(
            ["contest_id"], ["contests.id"], name="fk_jobs_contest_id_contests", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("contest_id", "kind", name="uq_jobs_contest_id_kind"),
        sa.CheckConstraint(
            "kind IN ('remind_submission', 'remind_voting', 'finalize')", name="ck_jobs_kind_valid"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'done', 'skipped', 'failed')", name="ck_jobs_status_valid"
        ),
    )
    op.create_index("ix_jobs_status_run_at", "jobs", ["status", "run_at"])

    op.create_table(
        "emails",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contest_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("to_address", sa.String(length=254), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_emails"),
        sa.ForeignKeyConstraint(
            ["contest_id"], ["contests.id"], name="fk_emails_contest_id_contests", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], name="fk_emails_recipient_id_users"),
        sa.UniqueConstraint(
            "contest_id", "recipient_id", "kind", name="uq_emails_contest_id_recipient_id_kind"
        ),
        sa.CheckConstraint(
            "kind IN ('reminder_submission', 'reminder_voting', 'final')", name="ck_emails_kind_valid"
        ),
    )
    op.create_index("ix_emails_recipient_created", "emails", ["recipient_id", "created_at"])

    # Конкурсы, созданные до этапа 5, получают задания с REMINDER_LEAD по умолчанию (24 ч).
    # Напоминание раньше начала своего раунда сразу пропускается (D-042); просроченные
    # задания обработчик выполнит или пропустит по правилам D-043.
    op.execute(
        """
        INSERT INTO jobs (contest_id, kind, run_at, status, attempts, note, finished_at)
        SELECT id, 'finalize', voting_deadline, 'pending', 0, NULL, NULL FROM contests
        UNION ALL
        SELECT id, 'remind_submission', submission_deadline - interval '24 hours',
               CASE WHEN submission_deadline - interval '24 hours' < created_at
                    THEN 'skipped' ELSE 'pending' END,
               0,
               CASE WHEN submission_deadline - interval '24 hours' < created_at
                    THEN 'раунд короче срока напоминания' END,
               CASE WHEN submission_deadline - interval '24 hours' < created_at THEN now() END
        FROM contests
        UNION ALL
        SELECT id, 'remind_voting', voting_deadline - interval '24 hours',
               CASE WHEN voting_deadline - interval '24 hours' < submission_deadline
                    THEN 'skipped' ELSE 'pending' END,
               0,
               CASE WHEN voting_deadline - interval '24 hours' < submission_deadline
                    THEN 'раунд короче срока напоминания' END,
               CASE WHEN voting_deadline - interval '24 hours' < submission_deadline THEN now() END
        FROM contests
        """
    )


def downgrade() -> None:
    op.drop_index("ix_emails_recipient_created", table_name="emails")
    op.drop_table("emails")
    op.drop_index("ix_jobs_status_run_at", table_name="jobs")
    op.drop_table("jobs")
