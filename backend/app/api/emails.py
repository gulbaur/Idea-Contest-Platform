"""Почтовая заглушка: «Входящие» каждого и журнал рассылки (D-016, D-045, D-063)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import func, or_, select, tuple_, update

from app.deps import ClockDep, CurrentUserDep, DbSession
from app.models import Contest, Email, EmailKind, Role, User
from app.schemas import IdPath

router = APIRouter(prefix="/api", tags=["emails"])

IdQuery = Annotated[int | None, Query(ge=1, le=2_147_483_647)]
Limit = Annotated[int, Query(ge=1, le=500)]

# Напоминания: по их получателям видно, кто ещё не подал идею или не голосовал (D-058).
REMINDERS = (EmailKind.REMINDER_SUBMISSION, EmailKind.REMINDER_VOTING)


class RecipientOut(BaseModel):
    id: int
    display_name: str


class EmailOut(BaseModel):
    id: int
    contest_id: int
    contest_topic: str
    recipient: RecipientOut
    to_address: str
    kind: str
    subject: str
    body: str
    created_at: datetime
    # Только во «Входящих»: когда получатель открыл письмо; в журнале — null.
    read_at: datetime | None = None


class UnreadOut(BaseModel):
    count: int


def _base(limit: int):
    return (
        select(Email, Contest.topic, User.display_name)
        .join(Contest, Contest.id == Email.contest_id)
        .join(User, User.id == Email.recipient_id)
        .order_by(Email.created_at.desc(), Email.id.desc())
        .limit(limit)
    )


def _page(statement, before_time: datetime | None, before_id: int | None):
    """Следующая порция — после письма (before_time, before_id) (D-059). Курсор задаёт клиент."""
    if (before_time is None) != (before_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="before_time и before_id передаются вместе",
        )
    if before_time is not None:
        statement = statement.where(tuple_(Email.created_at, Email.id) < tuple_(before_time, before_id))
    return statement


def _out(rows, *, with_read: bool) -> list[EmailOut]:
    return [
        EmailOut(
            id=email.id,
            contest_id=email.contest_id,
            contest_topic=topic,
            recipient=RecipientOut(id=email.recipient_id, display_name=name),
            to_address=email.to_address,
            kind=email.kind,
            subject=email.subject,
            body=email.body,
            created_at=email.created_at,
            read_at=email.read_at if with_read else None,
        )
        for email, topic, name in rows
    ]


@router.get("/emails", response_model=list[EmailOut])
async def inbox(
    current: CurrentUserDep,
    db: DbSession,
    contest_id: IdQuery = None,
    unread: bool = False,
    limit: Limit = 200,
    before_time: AwareDatetime | None = None,
    before_id: IdQuery = None,
) -> list[EmailOut]:
    """«Входящие»: только письма, адресованные текущему пользователю, — у любой роли (D-063).

    Письма идут от новых к старым порциями по `limit` (D-059).
    """
    statement = _page(_base(limit).where(Email.recipient_id == current.user.id), before_time, before_id)
    if contest_id is not None:
        statement = statement.where(Email.contest_id == contest_id)
    if unread:
        statement = statement.where(Email.read_at.is_(None))
    return _out((await db.execute(statement)).all(), with_read=True)


@router.get("/emails/journal", response_model=list[EmailOut])
async def journal(
    current: CurrentUserDep,
    db: DbSession,
    clock: ClockDep,
    contest_id: IdQuery = None,
    kind: EmailKind | None = None,
    recipient: Annotated[str | None, Query(max_length=100)] = None,
    limit: Limit = 200,
    before_time: AwareDatetime | None = None,
    before_id: IdQuery = None,
) -> list[EmailOut]:
    """Журнал рассылки — технический список всех писем; организатору и администратору (D-063).

    Напоминания незавершённого конкурса здесь не показываются: по их получателям видно, кто ещё
    не подал идею, а значит — кто автор поданных (D-058). После финала авторы раскрыты.
    """
    if current.user.role not in (Role.ORGANIZER, Role.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Журнал рассылки доступен организатору и администратору")
    statement = _page(_base(limit), before_time, before_id).where(
        or_(Email.kind.not_in(REMINDERS), Contest.voting_deadline <= clock.now())
    )
    if contest_id is not None:
        statement = statement.where(Email.contest_id == contest_id)
    if kind is not None:
        statement = statement.where(Email.kind == kind)
    if recipient and recipient.strip():
        # Поиск по имени и адресу; символы шаблона LIKE в запросе экранируются.
        needle = recipient.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{needle}%"
        statement = statement.where(
            or_(User.display_name.ilike(pattern, escape="\\"), Email.to_address.ilike(pattern, escape="\\"))
        )
    return _out((await db.execute(statement)).all(), with_read=False)


@router.get("/emails/unread-count", response_model=UnreadOut)
async def unread_count(current: CurrentUserDep, db: DbSession) -> UnreadOut:
    count = await db.scalar(
        select(func.count()).where(Email.recipient_id == current.user.id, Email.read_at.is_(None))
    )
    return UnreadOut(count=count)


@router.post("/emails/{email_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(email_id: IdPath, current: CurrentUserDep, db: DbSession, clock: ClockDep) -> Response:
    """Отметить своё письмо прочитанным. Чужое письмо — «не найдено», как и несуществующее."""
    result = await db.execute(
        update(Email)
        .where(Email.id == email_id, Email.recipient_id == current.user.id)
        .values(read_at=func.coalesce(Email.read_at, clock.now()))
        .returning(Email.id)
    )
    if result.first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Письмо не найдено")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/emails/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(current: CurrentUserDep, db: DbSession, clock: ClockDep) -> Response:
    await db.execute(
        update(Email)
        .where(Email.recipient_id == current.user.id, Email.read_at.is_(None))
        .values(read_at=clock.now())
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
