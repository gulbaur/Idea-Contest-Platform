"""Конкурсы: создание, список, снимок состояния (D-028), список сотрудников."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.access import ensure_organizer, load_visible_contest
from app.deps import ClockDep, CurrentUserDep, DbSession, HubDep
from app.domain import Phase, phase_at, ranking_key
from app.models import Contest, ContestParticipant, Idea, Role, User, Vote
from app.schemas import AuthorOut, ContestSummary, IdeaOut, IdPath, Title

router = APIRouter(prefix="/api", tags=["contests"])


class EmployeeOut(BaseModel):
    id: int
    login: str
    display_name: str


class ContestCreateIn(BaseModel):
    topic: Title
    # AwareDatetime: время без часового пояса отклоняется с 422 (D-032).
    submission_deadline: AwareDatetime
    voting_deadline: AwareDatetime
    # Не передан — участвуют все сотрудники (D-009).
    participant_ids: list[int] | None = Field(default=None, min_length=1)
    client_request_id: uuid.UUID


class ContestStats(BaseModel):
    """Статистика для экрана организатора (F8)."""

    participants_count: int
    ideas_count: int
    # Разные люди с хотя бы одним действующим голосом, а не число голосов (D-037).
    voters_count: int
    votes_count: int


class ContestSnapshot(BaseModel):
    contest: ContestSummary
    revision: int
    server_time: datetime
    ideas: list[IdeaOut]
    # Только для организатора; участникам — null.
    stats: ContestStats | None = None
    # Только после финала (D-035): первая идея по правилу «голоса → время подачи → id».
    winner_idea_id: int | None = None


def _summary(contest: Contest, now: datetime) -> ContestSummary:
    return ContestSummary(
        id=contest.id,
        topic=contest.topic,
        submission_deadline=contest.submission_deadline,
        voting_deadline=contest.voting_deadline,
        created_at=contest.created_at,
        phase=phase_at(contest.submission_deadline, contest.voting_deadline, now),
    )


def _invalid(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


@router.get("/users", response_model=list[EmployeeOut])
async def list_employees(current: CurrentUserDep, db: DbSession) -> list[EmployeeOut]:
    """Сотрудники для выбора участников при создании конкурса."""
    ensure_organizer(current.user)
    rows = await db.execute(
        select(User.id, User.login, User.display_name)
        .where(User.role == Role.EMPLOYEE)
        .order_by(User.display_name, User.id)
    )
    return [EmployeeOut(id=r.id, login=r.login, display_name=r.display_name) for r in rows]


@router.post("/contests", response_model=ContestSummary, status_code=status.HTTP_201_CREATED)
async def create_contest(
    payload: ContestCreateIn,
    response: Response,
    current: CurrentUserDep,
    db: DbSession,
    clock: ClockDep,
    hub: HubDep,
) -> ContestSummary:
    ensure_organizer(current.user)
    user = current.user
    now = clock.now()

    # Повтор того же запроса (двойное нажатие, повтор после обрыва сети) — вернуть уже созданное.
    existing = await db.scalar(
        select(Contest).where(
            Contest.created_by == user.id, Contest.client_request_id == payload.client_request_id
        )
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _summary(existing, now)

    if payload.submission_deadline <= now:
        raise _invalid("Срок окончания приёма идей должен быть в будущем")
    if payload.voting_deadline <= payload.submission_deadline:
        raise _invalid("Срок окончания голосования должен быть позже окончания приёма идей")

    employee_ids = set(
        (await db.scalars(select(User.id).where(User.role == Role.EMPLOYEE))).all()
    )
    if payload.participant_ids is None:
        participant_ids = employee_ids
    else:
        participant_ids = set(payload.participant_ids)
        unknown = sorted(participant_ids - employee_ids)
        if unknown:
            raise _invalid(f"Участниками могут быть только сотрудники; неверные id: {unknown}")
    if not participant_ids:
        raise _invalid("Нет сотрудников для участия в конкурсе")

    # ON CONFLICT DO NOTHING: если параллельный такой же запрос успел раньше, вставки не будет.
    contest_id = await db.scalar(
        insert(Contest)
        .values(
            topic=payload.topic,
            submission_deadline=payload.submission_deadline,
            voting_deadline=payload.voting_deadline,
            created_by=user.id,
            created_at=now,
            client_request_id=payload.client_request_id,
            revision=1,
        )
        .on_conflict_do_nothing(index_elements=["created_by", "client_request_id"])
        .returning(Contest.id)
    )
    if contest_id is None:
        # Параллельный такой же запрос уже создал конкурс. В режиме READ COMMITTED
        # следующий SELECT видит его зафиксированную строку.
        existing = await db.scalar(
            select(Contest).where(
                Contest.created_by == user.id,
                Contest.client_request_id == payload.client_request_id,
            )
        )
        response.status_code = status.HTTP_200_OK
        return _summary(existing, now)

    await db.execute(
        insert(ContestParticipant),
        [{"contest_id": contest_id, "user_id": uid} for uid in sorted(participant_ids)],
    )
    await db.commit()
    hub.contest_created(contest_id, participant_ids)  # только после COMMIT (D-039)
    contest = await db.get(Contest, contest_id)
    return _summary(contest, now)


@router.get("/contests", response_model=list[ContestSummary])
async def list_contests(current: CurrentUserDep, db: DbSession, clock: ClockDep) -> list[ContestSummary]:
    """Организатор видит все конкурсы, сотрудник — только те, где он участник."""
    statement = select(Contest).order_by(Contest.created_at.desc(), Contest.id.desc())
    if current.user.role != Role.ORGANIZER:
        statement = statement.join(
            ContestParticipant,
            (ContestParticipant.contest_id == Contest.id)
            & (ContestParticipant.user_id == current.user.id),
        )
    now = clock.now()
    return [_summary(c, now) for c in (await db.scalars(statement)).all()]


@router.get("/contests/{contest_id}", response_model=ContestSnapshot)
async def get_contest(
    contest_id: IdPath, current: CurrentUserDep, db: DbSession, clock: ClockDep
) -> ContestSnapshot:
    """Всё, что пользователь может видеть в конкурсе прямо сейчас (D-028).

    Что видно, решается здесь, на сервере (D-005, D-007, D-035):
    - подача: участник — только свои идеи; организатор — только счётчики;
    - голосование: все идеи без авторов; счёт голосов — только организатору;
    - финал: все идеи с авторами, счётом и победителем.
    """
    # Все запросы снимка видят одно состояние БД, поэтому revision соответствует данным.
    await db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    user = current.user
    contest = await load_visible_contest(db, contest_id, user)
    now = clock.now()
    phase = phase_at(contest.submission_deadline, contest.voting_deadline, now)
    is_organizer = user.role == Role.ORGANIZER

    statement = (
        select(Idea, User.display_name)
        .join(User, User.id == Idea.author_id)
        .where(Idea.contest_id == contest.id)
        .order_by(Idea.submitted_at, Idea.id)
    )
    if phase == Phase.SUBMISSION:
        if is_organizer:
            statement = None  # во время подачи организатор видит только число идей
        else:
            statement = statement.where(Idea.author_id == user.id)  # чужие идеи не читаются из БД

    # Результаты видны организатору с начала голосования и всем — после финала.
    show_results = phase == Phase.FINISHED or (is_organizer and phase == Phase.VOTING)

    votes_by_idea: dict[int, int] = {}
    if show_results:
        rows = await db.execute(
            select(Vote.idea_id, func.count())
            .where(Vote.contest_id == contest.id)
            .group_by(Vote.idea_id)
        )
        votes_by_idea = dict(rows.all())

    # Только собственные голоса пользователя — кто голосовал за что, не раскрывается (D-036).
    my_votes: set[int] = set()
    if not is_organizer and phase != Phase.SUBMISSION:
        my_votes = set(
            (
                await db.scalars(
                    select(Vote.idea_id).where(
                        Vote.contest_id == contest.id, Vote.voter_id == user.id
                    )
                )
            ).all()
        )

    ideas: list[IdeaOut] = []
    if statement is not None:
        for idea, author_name in (await db.execute(statement)).all():
            out = IdeaOut.model_validate(
                {
                    **_idea_fields(idea),
                    "is_mine": idea.author_id == user.id,
                    "voted_by_me": idea.id in my_votes,
                }
            )
            if phase == Phase.FINISHED:
                out.author = AuthorOut(id=idea.author_id, display_name=author_name)
            if show_results:
                out.votes_count = votes_by_idea.get(idea.id, 0)
            ideas.append(out)

    if show_results:
        ideas.sort(key=lambda i: ranking_key(i.votes_count, i.submitted_at, i.id))
    winner_idea_id = ideas[0].id if phase == Phase.FINISHED and ideas else None

    stats = None
    if is_organizer:
        stats = ContestStats(
            participants_count=await db.scalar(
                select(func.count()).where(ContestParticipant.contest_id == contest.id)
            ),
            ideas_count=await db.scalar(
                select(func.count()).select_from(Idea).where(Idea.contest_id == contest.id)
            ),
            voters_count=await db.scalar(
                select(func.count(func.distinct(Vote.voter_id))).where(
                    Vote.contest_id == contest.id
                )
            ),
            votes_count=await db.scalar(
                select(func.count()).select_from(Vote).where(Vote.contest_id == contest.id)
            ),
        )

    return ContestSnapshot(
        contest=_summary(contest, now),
        revision=contest.revision,
        server_time=now,
        ideas=ideas,
        stats=stats,
        winner_idea_id=winner_idea_id,
    )


def _idea_fields(idea: Idea) -> dict:
    return {
        "id": idea.id,
        "title": idea.title,
        "description": idea.description,
        "submitted_at": idea.submitted_at,
        "updated_at": idea.updated_at,
        "version": idea.version,
    }
