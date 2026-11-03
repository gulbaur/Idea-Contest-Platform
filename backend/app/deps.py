"""Общие зависимости FastAPI: часы и текущий пользователь."""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.db import get_db
from app.models import User, UserSession
from app.realtime import Hub
from app.security import hash_session_token


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_hub(request: Request) -> Hub:
    return request.app.state.hub


DbSession = Annotated[AsyncSession, Depends(get_db)]
ClockDep = Annotated[Clock, Depends(get_clock)]
HubDep = Annotated[Hub, Depends(get_hub)]

# auto_error=False: отсутствие заголовка обрабатываем сами, чтобы ответ был единообразным (401).
_bearer = HTTPBearer(auto_error=False, description="Токен из POST /api/auth/login")


@dataclass
class CurrentUser:
    user: User
    session_id: int


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Требуется вход",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def find_session(
    db: AsyncSession, token: str, now: datetime
) -> tuple[UserSession, User] | None:
    """Действующая сессия по токену и её пользователь, иначе None (HTTP и WebSocket)."""
    row = (
        await db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.token_hash == hash_session_token(token))
        )
    ).first()
    # Сессия действует строго до expires_at: в момент expires_at она уже недействительна.
    if row is None or now >= row[0].expires_at:
        return None
    return row[0], row[1]


async def get_current_user(
    db: DbSession,
    clock: ClockDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    """Определяет пользователя только по токену сессии (D-003).

    Идентификатор и роль берутся из БД по найденной сессии. Любые поля
    вроде `user_id` или `role`, присланные клиентом в запросе, здесь не читаются.
    """
    if credentials is None:
        raise _unauthorized()
    found = await find_session(db, credentials.credentials, clock.now())
    if found is None:
        raise _unauthorized()
    session, user = found
    # Завершаем короткую транзакцию чтения: обработчик начнёт свою с нуля и сможет
    # выбрать уровень изоляции (снимок) или взять блокировку конкурса (изменения).
    # expire_on_commit=False — загруженный объект user остаётся доступным.
    await db.commit()
    return CurrentUser(user=user, session_id=session.id)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
