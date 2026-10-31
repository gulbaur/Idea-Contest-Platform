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
