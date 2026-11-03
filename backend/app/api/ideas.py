"""Идеи: подача, правка, удаление (F2, F3, F19; D-029, D-031)."""

import uuid

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import conflict, forbidden, load_visible_contest, not_found
from app.deps import ClockDep, CurrentUser, CurrentUserDep, DbSession, HubDep
from app.domain import Phase, phase_at
from app.models import Contest, Idea, Role
from app.schemas import Description, IdeaOut, IdPath, Title

router = APIRouter(prefix="/api", tags=["ideas"])


class IdeaCreateIn(BaseModel):
    title: Title
    description: Description
    # Создаётся формой при открытии; повтор запроса с ним не создаёт вторую идею (D-031).
    client_request_id: uuid.UUID


class IdeaUpdateIn(BaseModel):
    title: Title
    description: Description
    # Версия, которую видел клиент; устаревшая версия → 409 (D-031).
    version: int


def _own_idea_out(idea: Idea) -> IdeaOut:
    return IdeaOut(
        id=idea.id,
        title=idea.title,
        description=idea.description,
        submitted_at=idea.submitted_at,
        updated_at=idea.updated_at,
        version=idea.version,
        is_mine=True,
    )


@router.post(
    "/contests/{contest_id}/ideas", response_model=IdeaOut, status_code=status.HTTP_201_CREATED
)
async def submit_idea(
    contest_id: IdPath,
    payload: IdeaCreateIn,
    response: Response,
    current: CurrentUserDep,
    db: DbSession,
    clock: ClockDep,
    hub: HubDep,
) -> IdeaOut:
    user_id = current.user.id
    contest = await load_visible_contest(db, contest_id, current.user, lock=True)
    if current.user.role == Role.ORGANIZER:
        raise forbidden("Организатор не подаёт идеи")

    # Повтор уже выполненной подачи возвращает ту же идею — даже если срок уже прошёл.
    existing = await db.scalar(
        select(Idea).where(
            Idea.author_id == user_id, Idea.client_request_id == payload.client_request_id
        )
    )
    if existing is not None:
        if existing.contest_id != contest.id:
            raise conflict("Этот client_request_id уже использован для другой идеи")
        response.status_code = status.HTTP_200_OK
        return _own_idea_out(existing)

    # «Сейчас» — после получения блокировки конкурса (D-029).
    now = clock.now()
    if phase_at(contest.submission_deadline, contest.voting_deadline, now) != Phase.SUBMISSION:
        raise conflict("Приём идей закрыт")

    idea_id = await db.scalar(
        insert(Idea)
        .values(
            contest_id=contest.id,
            author_id=user_id,
            title=payload.title,
            description=payload.description,
            submitted_at=now,
            updated_at=now,
            version=1,
            client_request_id=payload.client_request_id,
        )
        .on_conflict_do_nothing(index_elements=["author_id", "client_request_id"])
        .returning(Idea.id)
    )
    if idea_id is None:  # страховка: ограничение БД сработало раньше проверки выше
        existing = await db.scalar(
            select(Idea).where(
                Idea.author_id == user_id, Idea.client_request_id == payload.client_request_id
            )
        )
        response.status_code = status.HTTP_200_OK
        return _own_idea_out(existing)

    contest.revision += 1
    await db.commit()
    # Чужие идеи во время подачи не видны: сигнал — только организаторам и автору (D-039).
    await hub.contest_changed(contest.id, contest.revision, restrict_to=user_id)
    return _own_idea_out(await db.get(Idea, idea_id))


async def _lock_own_idea(
    db: AsyncSession, idea_id: int, current: CurrentUser
) -> tuple[Contest, Idea]:
    """Блокирует конкурс идеи и возвращает свежую версию идеи автора, иначе 404.

    Чужая идея и несуществующая идея неразличимы — обе дают 404 (D-030).
    """
    contest_id = await db.scalar(
        select(Idea.contest_id).where(Idea.id == idea_id, Idea.author_id == current.user.id)
    )
    if contest_id is None:
        raise not_found("Идея не найдена")
    contest = await load_visible_contest(db, contest_id, current.user, lock=True)
    # Перечитываем идею уже под блокировкой: другая вкладка могла изменить или удалить её.
    idea = await db.scalar(
        select(Idea).where(Idea.id == idea_id).execution_options(populate_existing=True)
    )
    if idea is None:
        raise not_found("Идея не найдена")
    return contest, idea


@router.put("/ideas/{idea_id}", response_model=IdeaOut)
async def update_idea(
    idea_id: IdPath,
    payload: IdeaUpdateIn,
    current: CurrentUserDep,
    db: DbSession,
    clock: ClockDep,
    hub: HubDep,
) -> IdeaOut:
    contest, idea = await _lock_own_idea(db, idea_id, current)

    now = clock.now()
    if phase_at(contest.submission_deadline, contest.voting_deadline, now) != Phase.SUBMISSION:
        raise conflict("Приём идей закрыт: идею больше нельзя изменить")

    if payload.version != idea.version:
        if (payload.title, payload.description) == (idea.title, idea.description):
            return _own_idea_out(idea)  # повтор уже применённой правки
        raise conflict(
            {
                "message": "Идея уже изменена в другой вкладке",
                "current": _own_idea_out(idea).model_dump(mode="json"),
            }
        )

    if (payload.title, payload.description) != (idea.title, idea.description):
        idea.title = payload.title
        idea.description = payload.description
        idea.version += 1
        idea.updated_at = now  # submitted_at не меняется: правило ничьей (D-008)
        contest.revision += 1
        await db.commit()
        await hub.contest_changed(contest.id, contest.revision, restrict_to=current.user.id)
    return _own_idea_out(idea)


@router.delete("/ideas/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_idea(
    idea_id: IdPath, current: CurrentUserDep, db: DbSession, clock: ClockDep, hub: HubDep
) -> Response:
    contest, idea = await _lock_own_idea(db, idea_id, current)

    now = clock.now()
    phase = phase_at(contest.submission_deadline, contest.voting_deadline, now)
    if phase == Phase.FINISHED:
        raise conflict("Конкурс завершён: идею больше нельзя удалить")

    # Голоса за идею (этап 3) удаляются в этой же транзакции каскадом БД (D-013).
    await db.execute(delete(Idea).where(Idea.id == idea.id))
    contest.revision += 1
    await db.commit()
    # Во время голосования идея исчезает у всех; во время подачи её видел только автор.
    restrict_to = current.user.id if phase == Phase.SUBMISSION else None
    await hub.contest_changed(contest.id, contest.revision, restrict_to=restrict_to)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
