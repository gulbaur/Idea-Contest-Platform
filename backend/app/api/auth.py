"""Вход, выход и «кто я» (D-003, D-023)."""

import asyncio
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.deps import ClockDep, CurrentUserDep, DbSession, HubDep
from app.models import FONTS, LOCALES, THEMES, AuditEvent, LoginThrottle, User, UserSession
from app.passwords import MAX_LENGTH, password_problem
from app.schemas import StorableText
from app.seed import DEMO_USERS
from app.security import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    # Логин уходит в запрос к БД — недопустимые для неё символы отклоняются (D-038).
    login: Annotated[str, Field(min_length=1, max_length=64), StorableText]
    password: str = Field(min_length=1, max_length=256)


class PreferencesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    theme: str
    font: str
    locale: str


class PreferencesIn(BaseModel):
    """Меняются только переданные поля (D-060). Неизвестное значение — 422."""

    model_config = ConfigDict(extra="forbid")

    theme: Literal[THEMES] | None = None
    font: Literal[FONTS] | None = None
    locale: Literal[LOCALES] | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    display_name: str
    role: str
    preferences: PreferencesOut

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            login=user.login,
            display_name=user.display_name,
            role=user.role,
            preferences=PreferencesOut.model_validate(user),
        )


class LoginOut(BaseModel):
    token: str
    expires_at: datetime
    user: UserOut


class DemoAccountOut(BaseModel):
    login: str
    display_name: str
    role: str


class DemoOut(BaseModel):
    """Демо-режим (D-059): публичный пароль и аккаунты для быстрого входа на странице входа."""

    enabled: bool
    password: str | None = None
    accounts: list[DemoAccountOut] = []


# Ограничение попыток входа (D-062).
MAX_FAILURES = 5
LOCK_TIME = timedelta(minutes=15)


def _too_many(locked_until: datetime, now: datetime) -> HTTPException:
    minutes = max(1, int((locked_until - now).total_seconds() + 59) // 60)
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Слишком много неудачных попыток входа. Попробуйте снова через {minutes} мин.",
        headers={"Retry-After": str(minutes * 60)},
    )


async def _record_failure(db, key: str, now: datetime) -> None:
    """+1 неудачная попытка; пятая подряд закрывает вход на LOCK_TIME. Атомарно для параллельных запросов."""
    failures = await db.scalar(
        pg_insert(LoginThrottle)
        .values(login=key, failures=1, locked_until=None)
        .on_conflict_do_update(index_elements=["login"], set_={"failures": LoginThrottle.failures + 1})
        .returning(LoginThrottle.failures)
    )
    if failures >= MAX_FAILURES:
        await db.execute(
            update(LoginThrottle)
            .where(LoginThrottle.login == key)
            .values(failures=0, locked_until=now + LOCK_TIME)
        )
    await db.commit()


def _new_session(db, user: User, request: Request, now: datetime) -> tuple[str, datetime]:
    token = new_session_token()
    expires_at = now + timedelta(hours=request.app.state.settings.session_ttl_hours)
    db.add(UserSession(user_id=user.id, token_hash=hash_session_token(token), created_at=now, expires_at=expires_at))
    user.last_login_at = now
    return token, expires_at


@router.post("/login", response_model=LoginOut)
async def login(payload: LoginIn, request: Request, db: DbSession, clock: ClockDep) -> LoginOut:
    key = payload.login.strip().lower()
    now = clock.now()
    throttle = await db.get(LoginThrottle, key)
    if throttle is not None and throttle.locked_until is not None and throttle.locked_until > now:
        raise _too_many(throttle.locked_until, now)
    user = await db.scalar(select(User).where(User.login == key))
    # Завершаем транзакцию чтения до проверки пароля: соединение возвращается в пул
    # и не простаивает десятки миллисекунд scrypt (D-038). Объект user остаётся доступен.
    await db.commit()
    # Пароль проверяется и для несуществующего, отключённого или ещё не задавшего пароль
    # пользователя (против хеша-пустышки): по ответу и его времени нельзя узнать,
    # какие логины существуют и в каком они состоянии (D-062).
    # scrypt занимает десятки миллисекунд процессора — выполняем в отдельном потоке,
    # чтобы не задерживать другие запросы и WebSocket в цикле событий.
    usable = user is not None and user.is_active and user.password_hash is not None
    password_ok = await asyncio.to_thread(
        verify_password, payload.password, user.password_hash if usable else DUMMY_PASSWORD_HASH
    )
    if not (usable and password_ok):
        await _record_failure(db, key, now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль"
        )

    await db.execute(delete(LoginThrottle).where(LoginThrottle.login == key))
    # Истёкшие сессии этого пользователя больше не действуют — удаляем их при входе,
    # чтобы таблица не росла бесконечно (D-059). Поиск по user_id идёт по индексу.
    await db.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= now)
    )
    token, expires_at = _new_session(db, user, request, now)
    await db.commit()
    return LoginOut(token=token, expires_at=expires_at, user=UserOut.of(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current: CurrentUserDep, db: DbSession, hub: HubDep) -> Response:
    # Удаляется только сессия этого токена: другие вкладки того же пользователя остаются в системе.
    await db.execute(delete(UserSession).where(UserSession.id == current.session_id))
    await db.commit()
    hub.close_session(current.session_id)  # WebSocket этой вкладки тоже закрывается (D-039)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/demo", response_model=DemoOut)
async def demo(request: Request, db: DbSession) -> DemoOut:
    """Без входа. Вне демо-режима (`SEED_DEMO_DATA=false`) пароль и аккаунты не раскрываются."""
    settings = request.app.state.settings
    if not settings.seed_demo_data:
        return DemoOut(enabled=False)
    order = {login: index for index, (login, _, _) in enumerate(DEMO_USERS)}
    users = (await db.scalars(select(User).where(User.login.in_(order)))).all()
    return DemoOut(
        enabled=True,
        password=settings.demo_password,
        accounts=[
            DemoAccountOut(login=u.login, display_name=u.display_name, role=u.role)
            for u in sorted(users, key=lambda u: order[u.login])
        ],
    )


@router.get("/me", response_model=UserOut)
async def me(current: CurrentUserDep) -> UserOut:
    return UserOut.of(current.user)


@router.patch("/me/preferences", response_model=UserOut)
async def update_preferences(payload: PreferencesIn, current: CurrentUserDep, db: DbSession) -> UserOut:
    """Тема, шрифт и язык текущего пользователя — для всех его вкладок и устройств (D-060)."""
    changes = payload.model_dump(exclude_none=True)
    user = await db.get(User, current.user.id, with_for_update=True)
    for field, value in changes.items():
        setattr(user, field, value)
    await db.commit()
    return UserOut.of(user)



# --- первый вход по ссылке и смена пароля (D-062) -------------------------------------

LINK_INVALID = "Ссылка недействительна или устарела — попросите администратора выдать новую"


class SetupCheckIn(BaseModel):
    token: str = Field(min_length=1, max_length=256)


class SetupCheckOut(BaseModel):
    login: str
    display_name: str


class SetupIn(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=MAX_LENGTH)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_LENGTH)
    new_password: str = Field(min_length=1, max_length=MAX_LENGTH)


def _invalid_password(problem: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=problem)


async def _user_by_link(db, token: str, now: datetime, *, lock: bool = False) -> User:
    statement = select(User).where(User.setup_token_hash == hash_session_token(token))
    if lock:
        statement = statement.with_for_update()
    user = await db.scalar(statement)
    if user is None or not user.is_active or user.setup_expires_at is None or user.setup_expires_at <= now:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=LINK_INVALID)
    return user


@router.post("/setup/check", response_model=SetupCheckOut)
async def setup_check(payload: SetupCheckIn, db: DbSession, clock: ClockDep) -> SetupCheckOut:
    """Без входа: для чьей учётной записи ссылка (чтобы показать имя на странице).

    Токен — в теле запроса, а не в адресе: адреса попадают в журналы серверов (как и в D-003).
    """
    user = await _user_by_link(db, payload.token, clock.now())
    return SetupCheckOut(login=user.login, display_name=user.display_name)


@router.post("/setup", response_model=LoginOut)
async def setup(payload: SetupIn, request: Request, db: DbSession, clock: ClockDep, hub: HubDep) -> LoginOut:
    """Задать пароль по одноразовой ссылке и сразу войти. Ссылка после этого не действует."""
    now = clock.now()
    # Блокировка строки: два одновременных перехода по одной ссылке — второй получит 404.
    user = await _user_by_link(db, payload.token, now, lock=True)
    problem = password_problem(payload.password, user.login)
    if problem:
        raise _invalid_password(problem)
    user.password_hash = await asyncio.to_thread(hash_password, payload.password)
    user.setup_token_hash = None
    user.setup_expires_at = None
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.add(AuditEvent(actor_id=user.id, action="password_set", target_user_id=user.id, details=None, created_at=now))
    token, expires_at = _new_session(db, user, request, now)
    await db.commit()
    hub.close_user(user.id)  # вкладки со старым паролем — выход (новая вкладка ещё не подключена)
    return LoginOut(token=token, expires_at=expires_at, user=UserOut.of(user))


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChangeIn, current: CurrentUserDep, db: DbSession, clock: ClockDep, hub: HubDep
) -> Response:
    """Смена пароля с вводом текущего. Остальные вкладки и устройства выходят, эта — остаётся."""
    user = current.user
    current_ok = await asyncio.to_thread(
        verify_password, payload.current_password, user.password_hash or DUMMY_PASSWORD_HASH
    )
    if not current_ok:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Текущий пароль указан неверно")
    problem = password_problem(payload.new_password, user.login)
    if problem:
        raise _invalid_password(problem)
    if payload.new_password == payload.current_password:
        raise _invalid_password("Новый пароль совпадает с текущим")
    new_hash = await asyncio.to_thread(hash_password, payload.new_password)
    now = clock.now()
    locked = await db.scalar(select(User).where(User.id == user.id).with_for_update())
    locked.password_hash = new_hash
    await db.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.id != current.session_id)
    )
    db.add(AuditEvent(actor_id=user.id, action="password_changed", target_user_id=user.id, details=None, created_at=now))
    await db.commit()
    hub.close_user(user.id, keep_session=current.session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
