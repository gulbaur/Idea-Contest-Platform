"""Таблицы БД. Схема создаётся миграциями Alembic (backend/migrations), не create_all()."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Явные имена ограничений: одинаковые в моделях и миграциях,
# поэтому тест сравнения схемы (test_migrations.py) не даёт ложных различий.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Role(StrEnum):
    ORGANIZER = "organizer"
    EMPLOYEE = "employee"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('organizer', 'employee')", name="role_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    """Сессия входа. Каждый вход (каждая вкладка) — отдельная строка (D-003)."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Хранится только SHA-256 токена; сам токен знает лишь клиент (D-023).
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Contest(Base):
    """Конкурс. Фаза не хранится, а вычисляется по срокам и серверному времени (D-007)."""

    __tablename__ = "contests"
    __table_args__ = (
        CheckConstraint("submission_deadline < voting_deadline", name="deadlines_ordered"),
        # Повтор запроса создания с тем же client_request_id не создаёт второй конкурс (D-031).
        UniqueConstraint(
            "created_by", "client_request_id", name="uq_contests_created_by_client_request_id"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(200))
    submission_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    voting_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    client_request_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # Номер версии состояния конкурса: +1 при каждом изменении внутри конкурса (D-013, D-029).
    revision: Mapped[int] = mapped_column(BigInteger)


class ContestParticipant(Base):
    """Список участников конкурса (D-009): только они подают идеи, голосуют и получают письма."""

    __tablename__ = "contest_participants"

    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)


class Idea(Base):
    __tablename__ = "ideas"
    __table_args__ = (
        UniqueConstraint(
            "author_id", "client_request_id", name="uq_ideas_author_id_client_request_id"
        ),
        # Порядок идей и правило ничьей: раньше поданная → меньший id (D-008).
        Index("ix_ideas_contest_order", "contest_id", "submitted_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contest_id: Mapped[int] = mapped_column(ForeignKey("contests.id", ondelete="CASCADE"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    # Время первой подачи; при правке не меняется (D-008).
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Версия для защиты от правки устаревших данных из другой вкладки (D-013, D-031).
    version: Mapped[int] = mapped_column(Integer)
    client_request_id: Mapped[uuid.UUID] = mapped_column(Uuid)


class Vote(Base):
    """Голос участника за идею (D-033).

    Первичный ключ (idea_id, voter_id): второй голос того же участника за ту же идею
    отвергает сама БД. При удалении идеи её голоса удаляются каскадом.
    """

    __tablename__ = "votes"
    __table_args__ = (Index("ix_votes_contest_voter", "contest_id", "voter_id"),)

    idea_id: Mapped[int] = mapped_column(
        ForeignKey("ideas.id", ondelete="CASCADE"), primary_key=True
    )
    voter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    contest_id: Mapped[int] = mapped_column(ForeignKey("contests.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class JobKind(StrEnum):
    REMIND_SUBMISSION = "remind_submission"
    REMIND_VOTING = "remind_voting"
    FINALIZE = "finalize"


class JobStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


class Job(Base):
    """Запланированное действие конкурса (D-042). Выполняет обработчик app/jobs.py (D-043)."""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("contest_id", "kind", name="uq_jobs_contest_id_kind"),
        CheckConstraint(
            "kind IN ('remind_submission', 'remind_voting', 'finalize')", name="kind_valid"
        ),
        CheckConstraint(
            "status IN ('pending', 'done', 'skipped', 'failed')", name="status_valid"
        ),
        # Поиск наступивших заданий: status = 'pending' AND run_at <= now.
        Index("ix_jobs_status_run_at", "status", "run_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contest_id: Mapped[int] = mapped_column(ForeignKey("contests.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Пояснение результата: сколько писем, почему пропущено (видно в БД).
    note: Mapped[str | None] = mapped_column(Text)


class EmailKind(StrEnum):
    REMINDER_SUBMISSION = "reminder_submission"
    REMINDER_VOTING = "reminder_voting"
    FINAL = "final"


class Email(Base):
    """Письмо почтовой заглушки (D-016, D-045): хранится в БД, реально не отправляется."""

    __tablename__ = "emails"
    __table_args__ = (
        # Одно письмо каждого вида на человека в конкурсе: напоминание на раунд, итог (D-012).
        UniqueConstraint(
            "contest_id", "recipient_id", "kind", name="uq_emails_contest_id_recipient_id_kind"
        ),
        CheckConstraint(
            "kind IN ('reminder_submission', 'reminder_voting', 'final')", name="kind_valid"
        ),
        Index("ix_emails_recipient_created", "recipient_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contest_id: Mapped[int] = mapped_column(ForeignKey("contests.id", ondelete="CASCADE"))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Адрес на момент отправки — так письмо выглядело бы в настоящей почте.
    to_address: Mapped[str] = mapped_column(String(254))
    kind: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
