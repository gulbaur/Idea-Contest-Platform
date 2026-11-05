"""Уведомления (D-063): новые виды писем, задание «голосование открыто», отметка «прочитано».

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_JOB_KINDS = "kind IN ('remind_submission', 'remind_voting', 'finalize')"
NEW_JOB_KINDS = "kind IN ('remind_submission', 'open_voting', 'remind_voting', 'finalize')"
OLD_EMAIL_KINDS = "kind IN ('reminder_submission', 'reminder_voting', 'final')"
NEW_EMAIL_KINDS = (
    "kind IN ('invitation', 'reminder_submission', 'voting_open', 'reminder_voting', 'final', "
    "'org_submission_soon', 'org_submission_closed', 'org_voting_soon', 'org_job_failed')"
)


def upgrade() -> None:
    op.drop_constraint("ck_jobs_kind_valid", "jobs", type_="check")
    op.create_check_constraint("kind_valid", "jobs", NEW_JOB_KINDS)
    op.drop_constraint("ck_emails_kind_valid", "emails", type_="check")
    op.create_check_constraint("kind_valid", "emails", NEW_EMAIL_KINDS)
    op.add_column("emails", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_emails_created_at_id", "emails", ["created_at", "id"])
    # Уже созданным конкурсам — задание «голосование открыто». Если приём идей уже закончился,
    # задание сразу пропущено: сообщать о начале голосования задним числом поздно.
    op.execute(
        """
        INSERT INTO jobs (contest_id, kind, run_at, status, attempts, note, finished_at)
        SELECT id, 'open_voting', submission_deadline,
               CASE WHEN submission_deadline > now() THEN 'pending' ELSE 'skipped' END,
               0,
               CASE WHEN submission_deadline > now() THEN NULL
                    ELSE 'конкурс создан до появления этого письма' END,
               CASE WHEN submission_deadline > now() THEN NULL ELSE now() END
        FROM contests
        ON CONFLICT (contest_id, kind) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM jobs WHERE kind = 'open_voting'")
    op.execute(
        "DELETE FROM emails WHERE kind NOT IN ('reminder_submission', 'reminder_voting', 'final') "
        "OR recipient_id IN (SELECT id FROM users WHERE role <> 'employee')"
    )
    op.drop_index("ix_emails_created_at_id", table_name="emails")
    op.drop_column("emails", "read_at")
    op.drop_constraint("ck_emails_kind_valid", "emails", type_="check")
    op.create_check_constraint("kind_valid", "emails", OLD_EMAIL_KINDS)
    op.drop_constraint("ck_jobs_kind_valid", "jobs", type_="check")
    op.create_check_constraint("kind_valid", "jobs", OLD_JOB_KINDS)
