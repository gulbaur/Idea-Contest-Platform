"""Таблицы БД. Схема создаётся миграциями Alembic (backend/migrations), не create_all()."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.sql import true

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
    ADMIN = "admin"  # управляет сотрудниками и ролями (D-062)
    ORGANIZER = "organizer"
    EMPLOYEE = "employee"


# Допустимые настройки вида (D-060); те же списки проверяет БД.
THEMES = ("system", "light", "dark")
FONTS = ("inter", "plex", "golos", "system")
LOCALES = ("ru", "en")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'organizer', 'employee')", name="role_valid"),
        CheckConstraint(_one_of("theme", THEMES), name="theme_valid"),
        CheckConstraint(_one_of("font", FONTS), name="font_valid"),
        CheckConstraint(_one_of("locale", LOCALES), name="locale_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    role: Mapped[str] = mapped_column(String(16))
    # Нет, пока приглашённый сотрудник не задал пароль по ссылке (D-062).
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Отключённый не входит и не получает писем; история (идеи, голоса, письма) остаётся.
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Одноразовая ссылка для задания пароля: хранится только SHA-256 токена (как у сессий).
    setup_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    setup_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Настройки вида (D-060): хранятся у пользователя, а не в браузере.
    theme: Mapped[str] = mapped_column(String(16), server_default="system")
    font: Mapped[str] = mapped_column(String(16), server_default="inter")
    locale: Mapped[str] = mapped_column(String(8), server_default="ru")


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
    # В момент окончания приёма идей: «голосование открыто» участникам, итог подачи организатору (D-063).
    OPEN_VOTING = "open_voting"
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
        CheckConstraint(_one_of("kind", tuple(k.value for k in JobKind)), name="kind_valid"),
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
    # Участникам.
    INVITATION = "invitation"  # вас включили в конкурс (D-063)
    REMINDER_SUBMISSION = "reminder_submission"
    VOTING_OPEN = "voting_open"  # приём идей завершён, можно голосовать (D-063)
    REMINDER_VOTING = "reminder_voting"
    FINAL = "final"  # итоги; организатору — тоже, в своём варианте
    # Организатору — создателю конкурса (D-063). Только числа, без имён до финала.
    ORG_SUBMISSION_SOON = "org_submission_soon"
    ORG_SUBMISSION_CLOSED = "org_submission_closed"
    ORG_VOTING_SOON = "org_voting_soon"
    ORG_JOB_FAILED = "org_job_failed"


class Email(Base):
    """Письмо почтовой заглушки (D-016, D-045): хранится в БД, реально не отправляется."""

    __tablename__ = "emails"
    __table_args__ = (
        # Одно письмо каждого вида на человека в конкурсе: напоминание на раунд, итог (D-012).
        UniqueConstraint(
            "contest_id", "recipient_id", "kind", name="uq_emails_contest_id_recipient_id_kind"
        ),
        CheckConstraint(_one_of("kind", tuple(k.value for k in EmailKind)), name="kind_valid"),
        Index("ix_emails_recipient_created", "recipient_id", "created_at"),
        # Журнал рассылки: все письма от новых к старым (D-063).
        Index("ix_emails_created_at_id", "created_at", "id"),
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
    # Когда получатель открыл письмо; null — не прочитано (D-063).
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginThrottle(Base):
    """Неудачные попытки входа по логину (D-062): после 5 подряд вход закрыт на 15 минут.

    Ключ — введённый логин, существует он или нет: иначе по ответу «слишком много попыток»
    можно было бы узнать, какие логины есть в системе.
    """

    __tablename__ = "login_throttle"

    login: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """Журнал действий с учётными записями (D-062): кто, когда, что и с кем сделал."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(32))
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
