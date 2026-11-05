"""Расписание конкурса и почтовая заглушка (D-015, D-042 … D-045).

- `plan_jobs` — задания нового конкурса; создаются в транзакции создания конкурса.
- `JobRunner` — фоновый обработчик: выполняет наступившие задания по одному,
  каждое в своей транзакции вместе с письмами.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.domain import Phase, phase_at, ranking_key
from app.models import (
    Contest,
    ContestParticipant,
    Email,
    EmailKind,
    Idea,
    Job,
    JobKind,
    JobStatus,
    User,
    Vote,
)
from app.realtime import Hub

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
MIN_SLEEP_SECONDS = 0.05
RETRY_STEP = timedelta(seconds=5)
SHORT_ROUND_NOTE = "раунд короче срока напоминания"


# --- план -------------------------------------------------------------------


def plan_jobs(
    contest_id: int,
    *,
    created_at: datetime,
    submission_deadline: datetime,
    voting_deadline: datetime,
    lead: timedelta,
) -> list[dict]:
    """Строки заданий нового конкурса (D-042).

    Напоминание, момент которого раньше начала раунда, сразу пропускается:
    раунд короче срока напоминания, напоминать «за сутки» уже поздно.
    """
    rounds = [
        (JobKind.REMIND_SUBMISSION, submission_deadline, created_at),
        (JobKind.REMIND_VOTING, voting_deadline, submission_deadline),
    ]
    rows = []
    for kind, deadline, round_start in rounds:
        run_at = deadline - lead
        too_short = run_at < round_start
        rows.append(
            _job_row(
                contest_id,
                kind,
                run_at,
                JobStatus.SKIPPED if too_short else JobStatus.PENDING,
                note=SHORT_ROUND_NOTE if too_short else None,
                finished_at=created_at if too_short else None,
            )
        )
    rows.append(_job_row(contest_id, JobKind.FINALIZE, voting_deadline, JobStatus.PENDING))
    return rows


def _job_row(contest_id, kind, run_at, status, *, note=None, finished_at=None) -> dict:
    return {
        "contest_id": contest_id,
        "kind": kind.value,
        "run_at": run_at,
        "status": status.value,
        "attempts": 0,
        "note": note,
        "finished_at": finished_at,
    }


# --- тексты писем -----------------------------------------------------------


def _when(moment: datetime) -> str:
    # Часовой пояс получателя серверу неизвестен — время в UTC с явной пометкой (D-044).
    return moment.astimezone(UTC).strftime("%d.%m.%Y %H:%M UTC")


def _votes(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        word = "голос"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        word = "голоса"
    else:
        word = "голосов"
    return f"{n} {word}"


@dataclass(frozen=True)
class RankedIdea:
    id: int
    title: str
    author_id: int
    author_name: str
    votes: int


async def ranked_ideas(db: AsyncSession, contest_id: int) -> list[RankedIdea]:
    """Идеи конкурса в порядке результатов (D-008): первая — победитель."""
    counts = dict(
        (
            await db.execute(
                select(Vote.idea_id, func.count()).where(Vote.contest_id == contest_id).group_by(Vote.idea_id)
            )
        ).all()
    )
    rows = (
        await db.execute(
            select(Idea, User.display_name)
            .join(User, User.id == Idea.author_id)
            .where(Idea.contest_id == contest_id)
        )
    ).all()
    rows.sort(key=lambda r: ranking_key(counts.get(r[0].id, 0), r[0].submitted_at, r[0].id))
    return [
        RankedIdea(idea.id, idea.title, idea.author_id, name, counts.get(idea.id, 0))
        for idea, name in rows
    ]


def _reminder_text(kind: JobKind, contest: Contest, user: User) -> tuple[str, str]:
    if kind == JobKind.REMIND_SUBMISSION:
        deadline = _when(contest.submission_deadline)
        return (
            f"Напоминание: приём идей закрывается {deadline}",
            f"Здравствуйте, {user.display_name}!\n\n"
            f"В конкурсе «{contest.topic}» приём идей закрывается {deadline}. "
            "Вы ещё не подали идею — успейте предложить свою.",
        )
    deadline = _when(contest.voting_deadline)
    return (
        f"Напоминание: голосование закрывается {deadline}",
        f"Здравствуйте, {user.display_name}!\n\n"
        f"В конкурсе «{contest.topic}» голосование закрывается {deadline}. "
        "Вы ещё не проголосовали — выберите идеи, которые вам нравятся.",
    )


def _final_text(contest: Contest, user: User, ranking: list[RankedIdea]) -> tuple[str, str]:
    greeting = f"Здравствуйте, {user.display_name}!\n\n"
    if not ranking:
        return (
            f"Итоги конкурса «{contest.topic}»",
            greeting + f"Конкурс «{contest.topic}» завершён. Идей не подано, победителя нет.",
        )
    winner = ranking[0]
    lines = [
        f"{place}. {idea.title} — {_votes(idea.votes)} — автор: {idea.author_name}"
        for place, idea in enumerate(ranking, start=1)
    ]
    results = (
        "Результаты:\n" + "\n".join(lines) + "\n\n"
        "При равенстве голосов побеждает идея, поданная раньше."
    )
    if winner.author_id == user.id:
        # Победитель получает то же одно итоговое письмо — в варианте «вы победили» (D-012).
        return (
            f"Ваша идея победила в конкурсе «{contest.topic}»",
            greeting
            + f"Поздравляем! Ваша идея «{winner.title}» победила в конкурсе «{contest.topic}» "
            f"({_votes(winner.votes)}).\n\n"
            + results,
        )
    return (
        f"Итоги конкурса «{contest.topic}»",
        greeting
        + f"Конкурс «{contest.topic}» завершён. Победила идея «{winner.title}» "
        f"(автор: {winner.author_name}, {_votes(winner.votes)}).\n\n"
        + results,
    )


# --- выполнение заданий -----------------------------------------------------


def _participants(contest_id: int):
    # Отключённым сотрудникам письма не отправляются (D-062); их идеи и голоса остаются.
    return (
        select(User)
        .join(
            ContestParticipant,
            (ContestParticipant.user_id == User.id) & (ContestParticipant.contest_id == contest_id),
        )
        .where(User.is_active)
        .order_by(User.id)
    )


@dataclass(frozen=True)
class JobOutcome:
    job_id: int
    kind: str
    status: str
    note: str | None
    recipient_ids: tuple[int, ...] = ()


class JobRunner:
    """Фоновый обработчик заданий (D-043)."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        clock: Clock,
        hub: Hub,
        max_sleep_seconds: float,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._clock = clock
        self._hub = hub
        self._max_sleep = max_sleep_seconds
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        wakeup = self._hub.contest_created_event()
        self._task = asyncio.create_task(self._run(wakeup))

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def run_due(self) -> list[JobOutcome]:
        """Выполняет все наступившие задания по одному; возвращает результаты."""
        outcomes = []
        while (outcome := await self.run_one()) is not None:
            outcomes.append(outcome)
        return outcomes

    async def run_one(self) -> JobOutcome | None:
        async with self._sessionmaker() as db:
            # SKIP LOCKED: задание, которое уже выполняет другая копия обработчика, пропускаем.
            job = await db.scalar(
                select(Job)
                .where(Job.status == JobStatus.PENDING, Job.run_at <= self._clock.now())
                .order_by(Job.run_at, Job.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            # Та же блокировка, что у изменяющих запросов (D-029): задание дожидается
            # начатых изменений — например, голоса, принятого за миллисекунду до срока.
            contest = await db.scalar(
                select(Contest).where(Contest.id == job.contest_id).with_for_update()
            )
            now = self._clock.now()  # после блокировок
            try:
                # Точка сохранения: при ошибке откатываются письма, но не блокировка задания.
                async with db.begin_nested():
                    status, note, recipients = await self.execute(db, job, contest, now)
            except Exception as exc:  # noqa: BLE001 — любая ошибка: повторить позже
                return await self._record_failure(db, job, now, exc)

            job.status = status
            job.note = note
            job.finished_at = now
            await db.commit()

        # Только после COMMIT (D-039): письма — получателям, расписание — организаторам.
        self._hub.mail_changed(recipients)
        self._hub.schedule_changed(job.contest_id)
        return JobOutcome(job.id, job.kind, status, note, tuple(recipients))

    async def _record_failure(
        self, db: AsyncSession, job: Job, now: datetime, exc: Exception
    ) -> JobOutcome:
        log.exception("Задание %s (%s) не выполнено", job.id, job.kind)
        job.attempts += 1
        job.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        if job.attempts >= MAX_ATTEMPTS:
            job.status = JobStatus.FAILED
            job.finished_at = now
        else:
            job.run_at = now + RETRY_STEP * job.attempts
        await db.commit()
        self._hub.schedule_changed(job.contest_id)
        return JobOutcome(job.id, job.kind, job.status, job.last_error)

    @staticmethod
    async def execute(
        db: AsyncSession, job: Job, contest: Contest, now: datetime
    ) -> tuple[str, str, list[int]]:
        """Выполняет задание в транзакции вызывающего: письма записаны, статус — вернуть.

        Конкурс должен быть заблокирован вызывающим. Используется обработчиком и демо-данными
        (app/demo.py), которые так «проигрывают» прошлые задания по тем же правилам.
        """
        phase = phase_at(contest.submission_deadline, contest.voting_deadline, now)
        kind = JobKind(job.kind)

        if kind == JobKind.FINALIZE:
            if phase != Phase.FINISHED:
                raise RuntimeError("финал запущен до срока голосования")
            ranking = await ranked_ideas(db, contest.id)
            users = (await db.scalars(_participants(contest.id))).all()
            letters = [(user, *_final_text(contest, user, ranking)) for user in users]
            sent = await JobRunner._send(db, contest, EmailKind.FINAL, letters, now)
            winner = f"победитель — идея {ranking[0].id}" if ranking else "идей нет"
            return JobStatus.DONE, f"писем: {len(sent)}; {winner}", sent

        # Напоминание: раунд ещё открыт? (простой сервера — D-043)
        round_phase = Phase.SUBMISSION if kind == JobKind.REMIND_SUBMISSION else Phase.VOTING
        if phase != round_phase:
            return JobStatus.SKIPPED, "раунд уже закрыт", []

        # Получатели — заново, по текущему состоянию (D-010, D-044).
        statement = _participants(contest.id)
        if kind == JobKind.REMIND_SUBMISSION:
            email_kind = EmailKind.REMINDER_SUBMISSION
            statement = statement.where(
                ~exists().where(Idea.contest_id == contest.id, Idea.author_id == User.id)
            )
        else:
            email_kind = EmailKind.REMINDER_VOTING
            has_ideas = await db.scalar(select(exists().where(Idea.contest_id == contest.id)))
            if not has_ideas:
                return JobStatus.SKIPPED, "идей нет — голосовать не за что", []
            statement = statement.where(
                ~exists().where(Vote.contest_id == contest.id, Vote.voter_id == User.id),
                # Голосовать можно только за чужие идеи: если чужих нет, напоминать не о чем.
                exists().where(Idea.contest_id == contest.id, Idea.author_id != User.id),
            )
        users = (await db.scalars(statement)).all()
        letters = [(user, *_reminder_text(kind, contest, user)) for user in users]
        sent = await JobRunner._send(db, contest, email_kind, letters, now)
        return JobStatus.DONE, f"писем: {len(sent)}", sent

    @staticmethod
    async def _send(
        db: AsyncSession,
        contest: Contest,
        kind: EmailKind,
        letters: list[tuple[User, str, str]],
        now: datetime,
    ) -> list[int]:
        """Записывает письма; уже существующее письмо того же вида не дублируется (D-012)."""
        if not letters:
            return []
        rows = [
            {
                "contest_id": contest.id,
                "recipient_id": user.id,
                "to_address": user.email,
                "kind": kind.value,
                "subject": subject,
                "body": body,
                "created_at": now,
            }
            for user, subject, body in letters
        ]
        inserted = await db.scalars(
            insert(Email)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["contest_id", "recipient_id", "kind"])
            .returning(Email.recipient_id)
        )
        return list(inserted.all())

    async def _seconds_until_next_job(self) -> float:
        async with self._sessionmaker() as db:
            nearest = await db.scalar(
                select(func.min(Job.run_at)).where(Job.status == JobStatus.PENDING)
            )
        if nearest is None:
            return self._max_sleep
        delay = (nearest - self._clock.now()).total_seconds()
        # Не меньше MIN_SLEEP_SECONDS: наступившее задание может быть занято другой копией
        # обработчика (SKIP LOCKED), и без паузы цикл крутился бы впустую.
        return min(self._max_sleep, max(MIN_SLEEP_SECONDS, delay))

    async def _run(self, wakeup: asyncio.Event) -> None:
        while True:
            wakeup.clear()  # до проверки: конкурс, созданный во время неё, снова разбудит
            delay = self._max_sleep
            try:
                await self.run_due()
                delay = await self._seconds_until_next_job()
            except Exception:  # noqa: BLE001 — например, БД недоступна; повторим позже
                log.exception("Ошибка обработчика заданий")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(wakeup.wait(), timeout=delay)
