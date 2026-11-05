"""Сотрудники и доступ — раздел администратора (D-062).

Открытой регистрации нет: учётную запись создаёт администратор, а пароль сотрудник задаёт
сам по одноразовой ссылке. Администратор пароля не знает и не видит.
"""

import re
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints
from sqlalchemy import delete, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import ClockDep, CurrentUserDep, DbSession, HubDep
from app.models import AuditEvent, Contest, ContestParticipant, Role, User, UserSession
from app.passwords import new_setup_token
from app.permissions import ensure_admin
from app.schemas import IdPath, StorableText

router = APIRouter(prefix="/api/admin", tags=["admin"])

SETUP_LINK_TTL = timedelta(hours=72)
# Роли в журнале действий — словами, а не кодами.
ROLE_NAMES = {"admin": "администратор", "organizer": "организатор", "employee": "сотрудник"}
_LOGIN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _login(value: str) -> str:
    value = value.strip().lower()
    if not _LOGIN.match(value):
        raise ValueError("Логин: 2–64 символа — латинские буквы, цифры, точка, дефис, подчёркивание")
    return value


def _email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not _EMAIL.match(value):
        raise ValueError("Укажите рабочую почту в виде name@company.com")
    return value


Login = Annotated[str, StorableText, AfterValidator(_login)]
EmailAddress = Annotated[str, StorableText, AfterValidator(_email)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128), StorableText]
RoleName = Literal["employee", "organizer", "admin"]


class StaffOut(BaseModel):
    id: int
    login: str
    display_name: str
    email: str
    role: str
    # invited — пароль ещё не задан; active — может входить; disabled — доступ отключён.
    status: Literal["invited", "active", "disabled"]
    created_at: datetime
    last_login_at: datetime | None
    # Незавершённые конкурсы, где человек участник: пока они идут, роль менять нельзя.
    active_contests: list[str]


class SetupLinkOut(BaseModel):
    """Одноразовая ссылка. Токен показывается один раз и в БД не хранится (только хеш)."""

    token: str
    expires_at: datetime


class StaffCreated(BaseModel):
    user: StaffOut
    setup: SetupLinkOut


class StaffCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: Login
    display_name: DisplayName
    email: EmailAddress
    role: RoleName = "employee"


class StaffUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: DisplayName | None = None
    email: EmailAddress | None = None
    role: RoleName | None = None


class AuditOut(BaseModel):
    id: int
    actor: str
    action: str
    target: str | None
    details: str | None
    created_at: datetime


def _status(user: User) -> str:
    if not user.is_active:
        return "disabled"
    return "active" if user.password_hash else "invited"


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def _active_contests(db: AsyncSession, user_ids: list[int], now: datetime) -> dict[int, list[str]]:
    rows = await db.execute(
        select(ContestParticipant.user_id, Contest.topic)
        .join(Contest, Contest.id == ContestParticipant.contest_id)
        .where(ContestParticipant.user_id.in_(user_ids), Contest.voting_deadline > now)
        .order_by(Contest.id)
    )
    result: dict[int, list[str]] = {}
    for user_id, topic in rows:
        result.setdefault(user_id, []).append(topic)
    return result


async def _out(db: AsyncSession, user: User, now: datetime) -> StaffOut:
    contests = await _active_contests(db, [user.id], now)
    return _staff(user, contests.get(user.id, []))


def _staff(user: User, contests: list[str]) -> StaffOut:
    return StaffOut(
        id=user.id,
        login=user.login,
        display_name=user.display_name,
        email=user.email,
        role=user.role,
        status=_status(user),
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        active_contests=contests,
    )


def audit(db: AsyncSession, actor: User, action: str, target: User | None, details: str | None, now: datetime) -> None:
    db.add(
        AuditEvent(
            actor_id=actor.id,
            action=action,
            target_user_id=target.id if target else None,
            details=details,
            created_at=now,
        )
    )


def _issue_link(user: User, now: datetime) -> SetupLinkOut:
    token, token_hash = new_setup_token()
    user.setup_token_hash = token_hash
    user.setup_expires_at = now + SETUP_LINK_TTL
    return SetupLinkOut(token=token, expires_at=user.setup_expires_at)


async def revoke_access(db: AsyncSession, user: User) -> None:
    """Удалить все сессии пользователя. WebSocket закрывает вызывающий после COMMIT."""
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))


# Ключ рекомендательной блокировки PostgreSQL для всех изменений учётных записей.
STAFF_LOCK = 0x5354_4146  # «STAF»


async def _serialize(db: AsyncSession, actor: User) -> None:
    """Изменения учётных записей — строго по очереди, и только действующим администратором.

    Без общей блокировки два администратора, одновременно отключающие друг друга, ловили
    взаимную блокировку строк в PostgreSQL (ответ 500), а правило «хотя бы один администратор»
    держалось лишь случайно (приёмка версии 2). Изменения учётных записей редки — очередь не мешает.
    Пока запрос ждал очереди, его автора могли отключить или понизить — перепроверяем.
    """
    await db.execute(select(func.pg_advisory_xact_lock(STAFF_LOCK)))
    still = await db.scalar(select(User).where(User.id == actor.id).execution_options(populate_existing=True))
    if still is None or not still.is_active or still.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Действие доступно только администратору")


async def _locked_user(db: AsyncSession, user_id: int, actor: User) -> User:
    await _serialize(db, actor)
    # Блокировка строки — её ждёт и создание конкурса, проверяющее участников (D-062), см. contests.py.
    user = await db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден")
    return user


async def _other_active_admins(db: AsyncSession, user: User) -> int:
    return await db.scalar(
        select(func.count()).where(User.role == Role.ADMIN, User.is_active, User.id != user.id)
    )


@router.get("/users", response_model=list[StaffOut])
async def list_staff(current: CurrentUserDep, db: DbSession, clock: ClockDep) -> list[StaffOut]:
    ensure_admin(current.user)
    users = (await db.scalars(select(User).order_by(User.display_name, User.id))).all()
    contests = await _active_contests(db, [u.id for u in users], clock.now())
    return [_staff(u, contests.get(u.id, [])) for u in users]


@router.post("/users", response_model=StaffCreated, status_code=status.HTTP_201_CREATED)
async def invite(payload: StaffCreateIn, current: CurrentUserDep, db: DbSession, clock: ClockDep) -> StaffCreated:
    """Новый сотрудник без пароля + одноразовая ссылка, по которой он задаст пароль сам."""
    ensure_admin(current.user)
    now = clock.now()
    await _serialize(db, current.user)
    if await db.scalar(select(exists().where(User.login == payload.login))):
        raise _conflict("Такой логин уже занят")
    if await db.scalar(select(exists().where(User.email == payload.email))):
        raise _conflict("Такая почта уже есть у другого сотрудника")
    user = User(
        login=payload.login,
        display_name=payload.display_name,
        email=payload.email,
        role=payload.role,
        password_hash=None,
        created_at=now,
    )
    db.add(user)
    link = _issue_link(user, now)
    await db.flush()
    audit(db, current.user, "user_invited", user, f"роль: {ROLE_NAMES[payload.role]}", now)
    try:
        await db.commit()
    except IntegrityError as exc:  # параллельное приглашение с тем же логином или почтой
        await db.rollback()
        raise _conflict("Такой логин или почта уже заняты") from exc
    return StaffCreated(user=_staff(user, []), setup=link)


@router.patch("/users/{user_id}", response_model=StaffOut)
async def update_staff(
    user_id: IdPath, payload: StaffUpdateIn, current: CurrentUserDep, db: DbSession, clock: ClockDep, hub: HubDep
) -> StaffOut:
    ensure_admin(current.user)
    now = clock.now()
    user = await _locked_user(db, user_id, current.user)
    changes = []

    if payload.role is not None and payload.role != user.role:
        if user.id == current.user.id:
            raise _conflict("Нельзя изменить собственную роль — попросите другого администратора")
        if user.role == Role.ADMIN and not await _other_active_admins(db, user):
            raise _conflict("Это последний администратор: без него управлять сотрудниками будет некому")
        # Пока человек участвует в незавершённом конкурсе, роль не меняется: став организатором,
        # он увидел бы живой счёт голосов там, где сам подавал идеи (D-005, D-062).
        busy = (await _active_contests(db, [user.id], now)).get(user.id, [])
        if busy:
            raise _conflict(
                "Роль можно сменить после завершения конкурсов, где сотрудник участвует: "
                + ", ".join(f"«{topic}»" for topic in busy)
            )
        changes.append(f"роль: {ROLE_NAMES[user.role]} → {ROLE_NAMES[payload.role]}")
        user.role = payload.role

    if payload.display_name is not None and payload.display_name != user.display_name:
        changes.append(f"имя: {user.display_name} → {payload.display_name}")
        user.display_name = payload.display_name

    if payload.email is not None and payload.email != user.email:
        if await db.scalar(select(exists().where(User.email == payload.email, User.id != user.id))):
            raise _conflict("Такая почта уже есть у другого сотрудника")
        changes.append(f"почта: {user.email} → {payload.email}")
        user.email = payload.email

    role_changed = any(change.startswith("роль") for change in changes)
    if role_changed:
        # Новая роль — новые права: все сессии завершаются, человек входит заново.
        await revoke_access(db, user)
    if changes:
        audit(db, current.user, "user_updated", user, "; ".join(changes), now)
    await db.commit()
    if role_changed:
        hub.close_user(user.id)
    return await _out(db, user, now)


@router.post("/users/{user_id}/disable", response_model=StaffOut)
async def disable(user_id: IdPath, current: CurrentUserDep, db: DbSession, clock: ClockDep, hub: HubDep) -> StaffOut:
    """Доступ закрывается сразу: сессии удаляются, открытые вкладки выходят. История остаётся."""
    ensure_admin(current.user)
    now = clock.now()
    user = await _locked_user(db, user_id, current.user)
    if user.id == current.user.id:
        raise _conflict("Нельзя отключить себя — попросите другого администратора")
    if user.role == Role.ADMIN and not await _other_active_admins(db, user):
        raise _conflict("Это последний администратор: без него управлять сотрудниками будет некому")
    if user.is_active:
        user.is_active = False
        user.setup_token_hash = None
        user.setup_expires_at = None
        await revoke_access(db, user)
        audit(db, current.user, "user_disabled", user, None, now)
    await db.commit()
    hub.close_user(user.id)
    return await _out(db, user, now)


@router.post("/users/{user_id}/enable", response_model=StaffOut)
async def enable(user_id: IdPath, current: CurrentUserDep, db: DbSession, clock: ClockDep) -> StaffOut:
    ensure_admin(current.user)
    now = clock.now()
    user = await _locked_user(db, user_id, current.user)
    if not user.is_active:
        user.is_active = True
        audit(db, current.user, "user_enabled", user, None, now)
    await db.commit()
    return await _out(db, user, now)


@router.post("/users/{user_id}/setup-link", response_model=StaffCreated)
async def reset(user_id: IdPath, current: CurrentUserDep, db: DbSession, clock: ClockDep, hub: HubDep) -> StaffCreated:
    """Новая ссылка для входа: прежняя ссылка и прежний пароль перестают действовать.

    Это и «отправить приглашение повторно», и «сбросить пароль» (забыт или мог утечь).
    """
    ensure_admin(current.user)
    now = clock.now()
    user = await _locked_user(db, user_id, current.user)
    if not user.is_active:
        raise _conflict("Доступ сотрудника отключён — сначала включите его")
    had_password = user.password_hash is not None
    user.password_hash = None
    link = _issue_link(user, now)
    await revoke_access(db, user)
    audit(db, current.user, "password_reset" if had_password else "invite_reissued", user, None, now)
    await db.commit()
    hub.close_user(user.id)
    return StaffCreated(user=await _out(db, user, now), setup=link)


@router.get("/audit", response_model=list[AuditOut])
async def audit_log(
    current: CurrentUserDep,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_id: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
) -> list[AuditOut]:
    """Журнал действий: кто, когда и что сделал с учётными записями. Новые сверху, порциями."""
    ensure_admin(current.user)
    actor = User.__table__.alias("actor")
    target = User.__table__.alias("target")
    statement = (
        select(AuditEvent, actor.c.display_name, target.c.display_name)
        .join(actor, actor.c.id == AuditEvent.actor_id)
        .outerjoin(target, target.c.id == AuditEvent.target_user_id)
        .order_by(AuditEvent.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        statement = statement.where(AuditEvent.id < before_id)
    return [
        AuditOut(id=e.id, actor=a, action=e.action, target=t, details=e.details, created_at=e.created_at)
        for e, a, t in (await db.execute(statement)).all()
    ]
