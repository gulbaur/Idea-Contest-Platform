"""Проверки доступа, общие для маршрутов конкурсов и идей (D-005, D-009, D-030)."""

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contest, ContestParticipant, Role, User


def not_found(detail: str = "Конкурс не найден") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def conflict(detail: str | dict) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def ensure_organizer(user: User) -> None:
    if user.role != Role.ORGANIZER:
        raise forbidden("Действие доступно только организатору")


async def is_participant(db: AsyncSession, contest_id: int, user_id: int) -> bool:
    return bool(
        await db.scalar(
            select(
                exists().where(
                    ContestParticipant.contest_id == contest_id,
                    ContestParticipant.user_id == user_id,
                )
            )
        )
    )


async def load_visible_contest(
    db: AsyncSession,
    contest_id: int,
    user: User,
    *,
    lock: bool = False,
    missing_detail: str = "Конкурс не найден",
) -> Contest:
    """Конкурс, который пользователь имеет право видеть, иначе 404.

    Организатор видит все конкурсы, сотрудник — только те, где он в списке участников.
    `lock=True` блокирует строку конкурса до конца транзакции (D-029): так все
    изменения внутри одного конкурса выполняются строго по очереди.
    `missing_detail` — текст 404: маршруты идей передают «Идея не найдена», чтобы
    ответ не отличался от ответа на несуществующую идею (D-038).
    """
    if user.role != Role.ORGANIZER and not await is_participant(db, contest_id, user.id):
        raise not_found(missing_detail)
    statement = select(Contest).where(Contest.id == contest_id)
    if lock:
        statement = statement.with_for_update()
    contest = await db.scalar(statement)
    if contest is None:
        raise not_found(missing_detail)
    return contest
