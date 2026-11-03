"""Вход, выход и «кто я» (D-003, D-023)."""

import asyncio
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from app.deps import ClockDep, CurrentUserDep, DbSession
from app.models import User, UserSession
from app.schemas import StorableText
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


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    display_name: str
    role: str


class LoginOut(BaseModel):
    token: str
    expires_at: datetime
    user: UserOut


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
    return LoginOut(token=token, expires_at=expires_at, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current: CurrentUserDep, db: DbSession) -> Response:
    # Удаляется только сессия этого токена: другие вкладки того же пользователя остаются в системе.
    await db.execute(delete(UserSession).where(UserSession.id == current.session_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def me(current: CurrentUserDep) -> UserOut:
    return UserOut.model_validate(current.user)
