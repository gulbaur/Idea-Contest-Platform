"""Вход, выход и «кто я» (D-003, D-023)."""

import asyncio
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from app.deps import ClockDep, CurrentUserDep, DbSession, HubDep
from app.models import FONTS, LOCALES, THEMES, User, UserSession
from app.schemas import StorableText
from app.seed import DEMO_USERS
from app.security import (
    DUMMY_PASSWORD_HASH,
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


@router.post("/login", response_model=LoginOut)
async def login(payload: LoginIn, request: Request, db: DbSession, clock: ClockDep) -> LoginOut:
    user = await db.scalar(select(User).where(User.login == payload.login.strip().lower()))
    # Завершаем транзакцию чтения до проверки пароля: соединение возвращается в пул
    # и не простаивает десятки миллисекунд scrypt (D-038). Объект user остаётся доступен.
    await db.commit()
    # Пароль проверяется и для несуществующего логина (против хеша-пустышки),
    # чтобы по времени ответа нельзя было узнать, какие логины существуют.
    # scrypt занимает десятки миллисекунд процессора — выполняем в отдельном потоке,
    # чтобы не задерживать другие запросы и WebSocket в цикле событий.
    password_ok = await asyncio.to_thread(
        verify_password, payload.password, user.password_hash if user else DUMMY_PASSWORD_HASH
    )
    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль"
        )

    token = new_session_token()
    now = clock.now()
    # Истёкшие сессии этого пользователя больше не действуют — удаляем их при входе,
    # чтобы таблица не росла бесконечно (D-059). Поиск по user_id идёт по индексу.
    await db.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= now)
    )
    expires_at = now + timedelta(hours=request.app.state.settings.session_ttl_hours)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            created_at=now,
            expires_at=expires_at,
        )
    )
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
