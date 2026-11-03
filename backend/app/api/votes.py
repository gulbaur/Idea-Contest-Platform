"""Голосование: отдать и отозвать голос (F5, F13, F14; D-033, D-034)."""

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import conflict, forbidden, load_visible_contest, not_found
from app.clock import Clock
from app.deps import ClockDep, CurrentUser, CurrentUserDep, DbSession
from app.domain import Phase, phase_at
from app.models import Contest, Idea, Role, Vote
from app.schemas import IdPath

router = APIRouter(prefix="/api", tags=["votes"])

IDEA_NOT_FOUND = "Идея не найдена"


class VoteOut(BaseModel):
    idea_id: int
    voted: bool


async def _lock_for_voting(
    db: AsyncSession, idea_id: int, current: CurrentUser, clock: Clock
) -> tuple[Contest, Idea]:
    """Блокирует конкурс идеи и проверяет, что голосовать (или отзывать голос) можно сейчас.

    Идея, которую пользователь не может видеть, неотличима от несуществующей: и идея
    в чужом конкурсе, и чужая идея во время подачи дают тот же 404 (D-038).
    """
    contest_id = await db.scalar(select(Idea.contest_id).where(Idea.id == idea_id))
    if contest_id is None:
        raise not_found(IDEA_NOT_FOUND)
    contest = await load_visible_contest(
        db, contest_id, current.user, lock=True, missing_detail=IDEA_NOT_FOUND
    )
    if current.user.role == Role.ORGANIZER:
        raise forbidden("Организатор не голосует")

    # Под блокировкой перечитываем идею: автор мог удалить её, пока запрос ждал очереди.
    idea = await db.scalar(select(Idea).where(Idea.id == idea_id))
    if idea is None:
        raise not_found(IDEA_NOT_FOUND)

    # «Сейчас» — после получения блокировки (D-029).
    phase = phase_at(contest.submission_deadline, contest.voting_deadline, clock.now())
    if phase == Phase.SUBMISSION:
        if idea.author_id != current.user.id:
            raise not_found(IDEA_NOT_FOUND)  # во время подачи чужие идеи не видны
        raise conflict("Голосование ещё не началось")
    if phase == Phase.FINISHED:
        raise conflict("Голосование закрыто")
    return contest, idea


@router.post("/ideas/{idea_id}/vote", response_model=VoteOut, status_code=status.HTTP_201_CREATED)
async def vote(
    idea_id: IdPath, response: Response, current: CurrentUserDep, db: DbSession, clock: ClockDep
) -> VoteOut:
    contest, idea = await _lock_for_voting(db, idea_id, current, clock)
    if idea.author_id == current.user.id:
        raise forbidden("Нельзя голосовать за свою идею")

    # Второй голос за ту же идею отвергает первичный ключ (idea_id, voter_id);
    # ON CONFLICT DO NOTHING превращает повтор в «ничего не делать» вместо ошибки.
    inserted = await db.scalar(
        insert(Vote)
        .values(
            idea_id=idea.id,
            voter_id=current.user.id,
            contest_id=contest.id,
            created_at=clock.now(),
        )
        .on_conflict_do_nothing(index_elements=["idea_id", "voter_id"])
        .returning(Vote.idea_id)
    )
    if inserted is None:
        response.status_code = status.HTTP_200_OK  # голос уже был — повтор ничего не меняет
        return VoteOut(idea_id=idea.id, voted=True)

    contest.revision += 1
    await db.commit()
    return VoteOut(idea_id=idea.id, voted=True)


@router.delete("/ideas/{idea_id}/vote", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_vote(
    idea_id: IdPath, current: CurrentUserDep, db: DbSession, clock: ClockDep
) -> Response:
    contest, idea = await _lock_for_voting(db, idea_id, current, clock)

    deleted = await db.scalar(
        delete(Vote)
        .where(Vote.idea_id == idea.id, Vote.voter_id == current.user.id)
        .returning(Vote.idea_id)
    )
    if deleted is not None:  # повторный отзыв ничего не удаляет и revision не меняет
        contest.revision += 1
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
