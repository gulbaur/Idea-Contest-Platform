"""Конкурсы: создание, список, снимок состояния (D-028), список сотрудников."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import ensure_organizer, load_visible_contest, request_id_reused
from app.deps import ClockDep, CurrentUserDep, DbSession, HubDep
from app.domain import Phase, phase_at, ranking_key
from app.jobs import plan_jobs, send_invitations
from app.models import Contest, ContestParticipant, Idea, Job, JobKind, Role, User, Vote
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


class ParticipantOut(BaseModel):
    id: int
    display_name: str


class ScheduleItem(BaseModel):
    """Задание расписания для экрана организатора (D-051)."""

    kind: str
    run_at: datetime
    status: str
    finished_at: datetime | None
    note: str | None


class ContestSnapshot(BaseModel):
    contest: ContestSummary
    revision: int
    server_time: datetime
    ideas: list[IdeaOut]
    # Только для организатора; участникам — null.
    stats: ContestStats | None = None
    schedule: list[ScheduleItem] | None = None
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
    """Сотрудники для выбора участников при создании конкурса — только с действующим доступом."""
    ensure_organizer(current.user)
    rows = await db.execute(
        select(User.id, User.login, User.display_name)
        .where(User.role == Role.EMPLOYEE, User.is_active)
        .order_by(User.display_name, User.id)
    )
    return [EmployeeOut(id=r.id, login=r.login, display_name=r.display_name) for r in rows]


async def _employee_ids(db: AsyncSession, *, lock: bool = False) -> set[int]:
    """Сотрудники, которых можно включить в конкурс: роль «сотрудник» и доступ не отключён.

    `lock=True` — блокировка строк «на чтение» до конца транзакции (D-062): пока конкурс
    создаётся, администратор не сменит роль и не отключит этих людей, а если уже начал —
    создание дождётся и увидит итог. Так участник идущего конкурса не станет организатором.
    """
    statement = select(User.id).where(User.role == Role.EMPLOYEE, User.is_active)
    if lock:
        statement = statement.with_for_update(read=True)
    return set((await db.scalars(statement)).all())


async def _replayed(
    db: AsyncSession, existing: Contest, payload: ContestCreateIn, now: datetime
) -> ContestSummary:
    """Повтор того же запроса → уже созданный конкурс; тот же идентификатор с другой темой,
    сроками или участниками → 409, второй конкурс не создаётся (D-053)."""
    participants = set(
        (
            await db.scalars(
                select(ContestParticipant.user_id).where(ContestParticipant.contest_id == existing.id)
            )
        ).all()
    )
    requested = (
        await _employee_ids(db) if payload.participant_ids is None else set(payload.participant_ids)
    )
    same = (existing.topic, existing.submission_deadline, existing.voting_deadline) == (
        payload.topic,
        payload.submission_deadline,
        payload.voting_deadline,
    )
    if not same or participants != requested:
        raise request_id_reused()
    return _summary(existing, now)


@router.post("/contests", response_model=ContestSummary, status_code=status.HTTP_201_CREATED)
async def create_contest(
    payload: ContestCreateIn,
    request: Request,
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
        return await _replayed(db, existing, payload, now)

    if payload.submission_deadline <= now:
        raise _invalid("Срок окончания приёма идей должен быть в будущем")
    if payload.voting_deadline <= payload.submission_deadline:
        raise _invalid("Срок окончания голосования должен быть позже окончания приёма идей")

    employee_ids = await _employee_ids(db, lock=True)
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
        return await _replayed(db, existing, payload, now)

    await db.execute(
        insert(ContestParticipant),
        [{"contest_id": contest_id, "user_id": uid} for uid in sorted(participant_ids)],
    )
    # Расписание создаётся в той же транзакции: конкурс без заданий невозможен (D-042).
    await db.execute(
        insert(Job),
        plan_jobs(
            contest_id,
            created_at=now,
            submission_deadline=payload.submission_deadline,
            voting_deadline=payload.voting_deadline,
            lead=request.app.state.settings.reminder_lead,
        ),
    )
    contest = await db.get(Contest, contest_id)
    invited = await send_invitations(db, contest, now)  # в той же транзакции: конкурс без писем невозможен
    await db.commit()
    hub.contest_created(contest_id, participant_ids)  # только после COMMIT (D-039)
    hub.mail_changed(invited)
    return _summary(contest, now)


class ListStats(BaseModel):
    """Счётчики строки списка для организатора — те же, что в статистике конкурса (F8)."""

    participants_count: int
    ideas_count: int
    # Число проголосовавших — только с начала голосования, как на экране конкурса.
    voters_count: int | None


class MyParticipation(BaseModel):
    """Участие текущего сотрудника — только его собственные действия (D-061)."""

    ideas_count: int
    votes_count: int
    # Есть ли за кого голосовать (чужие идеи). Только во время голосования, иначе false:
    # во время подачи даже число чужих идей участнику не раскрывается (D-005).
    can_vote: bool


class ContestListItem(ContestSummary):
    stats: ListStats | None = None  # только организатору
    my: MyParticipation | None = None  # только участнику


async def _counts(db: AsyncSession, statement) -> dict[int, int]:
    return dict((await db.execute(statement)).all())


@router.get("/contests", response_model=list[ContestListItem])
async def list_contests(current: CurrentUserDep, db: DbSession, clock: ClockDep) -> list[ContestListItem]:
    """Организатор видит все конкурсы, сотрудник — только те, где он участник.

    Счётчики считаются несколькими групповыми запросами на весь список, а не запросом
    на каждый конкурс (D-061). Что видно, решают те же правила, что и для снимка.
    """
    user = current.user
    is_organizer = user.role == Role.ORGANIZER
    # Все запросы видят одно состояние БД, как и снимок конкурса.
    await db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    statement = select(Contest).order_by(Contest.created_at.desc(), Contest.id.desc())
    if not is_organizer:
        statement = statement.join(
            ContestParticipant,
            (ContestParticipant.contest_id == Contest.id) & (ContestParticipant.user_id == user.id),
        )
    contests = (await db.scalars(statement)).all()
    now = clock.now()
    if not contests:
        return []
    ids = [c.id for c in contests]

    def per_contest(column, *conditions):
        return select(column, func.count()).where(column.in_(ids), *conditions).group_by(column)

    items = []
    if is_organizer:
        participants = await _counts(db, per_contest(ContestParticipant.contest_id))
        ideas = await _counts(db, per_contest(Idea.contest_id))
        voters = await _counts(
            db,
            select(Vote.contest_id, func.count(func.distinct(Vote.voter_id)))
            .where(Vote.contest_id.in_(ids))
            .group_by(Vote.contest_id),
        )
        for contest in contests:
            summary = _summary(contest, now)
            items.append(
                ContestListItem(
                    **summary.model_dump(),
                    stats=ListStats(
                        participants_count=participants.get(contest.id, 0),
                        ideas_count=ideas.get(contest.id, 0),
                        voters_count=None if summary.phase == Phase.SUBMISSION else voters.get(contest.id, 0),
                    ),
                )
            )
        return items

    my_ideas = await _counts(db, per_contest(Idea.contest_id, Idea.author_id == user.id))
    my_votes = await _counts(db, per_contest(Vote.contest_id, Vote.voter_id == user.id))
    others = await _counts(db, per_contest(Idea.contest_id, Idea.author_id != user.id))
    for contest in contests:
        summary = _summary(contest, now)
        items.append(
            ContestListItem(
                **summary.model_dump(),
                my=MyParticipation(
                    ideas_count=my_ideas.get(contest.id, 0),
                    votes_count=my_votes.get(contest.id, 0),
                    can_vote=summary.phase == Phase.VOTING and others.get(contest.id, 0) > 0,
                ),
            )
        )
    return items


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
                    **_idea_fields(idea, own=idea.author_id == user.id),
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

    stats = schedule = None
    if is_organizer:
        order = {JobKind.REMIND_SUBMISSION: 0, JobKind.OPEN_VOTING: 1, JobKind.REMIND_VOTING: 2, JobKind.FINALIZE: 3}
        jobs = (await db.scalars(select(Job).where(Job.contest_id == contest.id))).all()
        schedule = [
            ScheduleItem(
                kind=job.kind,
                run_at=job.run_at,
                status=job.status,
                finished_at=job.finished_at,
                note=job.note,
            )
            for job in sorted(jobs, key=lambda j: order[JobKind(j.kind)])
        ]
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
        schedule=schedule,
        winner_idea_id=winner_idea_id,
    )


@router.get("/contests/{contest_id}/participants", response_model=list[ParticipantOut])
async def list_participants(
    contest_id: IdPath, current: CurrentUserDep, db: DbSession
) -> list[ParticipantOut]:
    """Участники конкурса — только организатору (D-051).

    Отдельно от снимка: в снимке нет имён до финала, и это проверяется тестами анонимности.
    """
    ensure_organizer(current.user)
    contest = await load_visible_contest(db, contest_id, current.user)
    rows = await db.execute(
        select(User.id, User.display_name)
        .join(ContestParticipant, ContestParticipant.user_id == User.id)
        .where(ContestParticipant.contest_id == contest.id)
        .order_by(User.display_name, User.id)
    )
    return [ParticipantOut(id=row.id, display_name=row.display_name) for row in rows]


def _idea_fields(idea: Idea, *, own: bool) -> dict:
    # Время и номер правки нужны только автору (для правки). У чужих идей они скрыты:
    # иначе видно, кто и когда правил идею, — лишняя зацепка к авторству (D-058).
    return {
        "id": idea.id,
        "title": idea.title,
        "description": idea.description,
        "submitted_at": idea.submitted_at,
        "updated_at": idea.updated_at if own else None,
        "version": idea.version if own else None,
    }
