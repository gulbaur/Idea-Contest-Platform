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

from app import mail_en
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
    Role,
    User,
    Vote,
)
from app.realtime import Hub

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
JOB_TITLES = {
    JobKind.REMIND_SUBMISSION: "напоминание о подаче идей",
    JobKind.OPEN_VOTING: "начало голосования",
    JobKind.REMIND_VOTING: "напоминание о голосовании",
    JobKind.FINALIZE: "итоги и письма участникам",
}
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
    rows.append(_job_row(contest_id, JobKind.OPEN_VOTING, submission_deadline, JobStatus.PENDING))
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
    # Письмо — на языке получателя (D-065).
    if user.locale == "en":
        return mail_en.reminder(kind.value, contest.topic, user.display_name, contest.submission_deadline, contest.voting_deadline)
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


def invitation_text(contest: Contest, user: User) -> tuple[str, str]:
    if user.locale == "en":
        return mail_en.invitation(contest.topic, user.display_name, contest.submission_deadline, contest.voting_deadline)
    return (
        f"Вас пригласили в конкурс идей «{contest.topic}»",
        f"Здравствуйте, {user.display_name}!\n\n"
        f"Вас включили в конкурс идей «{contest.topic}».\n\n"
        f"Приём идей — до {_when(contest.submission_deadline)}.\n"
        f"Голосование — до {_when(contest.voting_deadline)}.\n\n"
        "Предложите свою идею: до голосования её видите только вы, "
        "а авторы раскрываются только после подведения итогов.",
    )


def _voting_open_text(contest: Contest, user: User, ideas: int) -> tuple[str, str]:
    if user.locale == "en":
        return mail_en.voting_open(contest.topic, user.display_name, ideas, contest.voting_deadline)
    return (
        f"Голосование открыто: «{contest.topic}»",
        f"Здравствуйте, {user.display_name}!\n\n"
        f"Приём идей в конкурсе «{contest.topic}» завершён, подано {_ideas(ideas)}. "
        f"Голосование открыто до {_when(contest.voting_deadline)}.\n\n"
        "Голосовать можно за любые чужие идеи — по одному голосу за каждую. Авторы скрыты до финала.",
    )


def _ideas(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        word = "идея"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        word = "идеи"
    else:
        word = "идей"
    return f"{n} {word}"


def _organizer_text(kind: EmailKind, contest: Contest, user: User, facts: dict) -> tuple[str, str]:
    """Письма организатору (D-063). До финала — только числа, которые он и так видит на экране."""
    if user.locale == "en":
        return mail_en.organizer(
            kind.value, contest.topic, user.display_name, facts, contest.submission_deadline, contest.voting_deadline
        )
    hello = f"Здравствуйте, {user.display_name}!\n\n"
    topic = contest.topic
    if kind == EmailKind.ORG_SUBMISSION_SOON:
        return (
            f"Приём идей закрывается {_when(contest.submission_deadline)}: «{topic}»",
            hello
            + f"В конкурсе «{topic}» приём идей закрывается {_when(contest.submission_deadline)}.\n"
            f"Сейчас подано {_ideas(facts['ideas'])}; участников — {facts['participants']}.\n"
            f"Напоминание отправлено участникам без идей: {facts['reminded']}.",
        )
    if kind == EmailKind.ORG_SUBMISSION_CLOSED:
        if not facts["ideas"]:
            return (
                f"Идей не подано: «{topic}»",
                hello
                + f"Приём идей в конкурсе «{topic}» завершён, но идей не подано. Голосовать не за что: "
                f"{_when(contest.voting_deadline)} конкурс завершится без победителя.",
            )
        return (
            f"Приём идей завершён, голосование открыто: «{topic}»",
            hello
            + f"Приём идей в конкурсе «{topic}» завершён: подано {_ideas(facts['ideas'])}.\n"
            f"Голосование открыто до {_when(contest.voting_deadline)}; участникам отправлено письмо.",
        )
    if kind == EmailKind.ORG_VOTING_SOON:
        return (
            f"Голосование закрывается {_when(contest.voting_deadline)}: «{topic}»",
            hello
            + f"В конкурсе «{topic}» голосование закрывается {_when(contest.voting_deadline)}.\n"
            f"Проголосовали {facts['voters']} из {facts['participants']}. "
            f"Напоминание отправлено тем, кто ещё не голосовал: {facts['reminded']}.",
        )
    return (
        f"Сбой рассылки: «{topic}»",
        hello
        + f"В конкурсе «{topic}» не выполнено задание «{JOB_TITLES[JobKind(facts['job'])]}» после нескольких попыток: "
        "письма участникам могли не уйти. Подробности — в расписании на странице конкурса.",
    )


def _final_text(contest: Contest, user: User, ranking: list[RankedIdea]) -> tuple[str, str]:
    if user.locale == "en":
        return mail_en.final(
            contest.topic,
            user.display_name,
            ranking,
            is_organizer=user.role == Role.ORGANIZER,
            is_winner=bool(ranking) and ranking[0].author_id == user.id,
        )
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
    if user.role == Role.ORGANIZER:
        return (
            f"Конкурс завершён: «{contest.topic}»",
            greeting
            + f"Конкурс «{contest.topic}» завершён. Победила идея «{winner.title}» "
            f"(автор: {winner.author_name}, {_votes(winner.votes)}). Участникам отправлены итоговые письма.\n\n"
            + results,
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


async def send_invitations(db: AsyncSession, contest: Contest, now: datetime) -> list[int]:
    """Письмо «вас пригласили» участникам нового конкурса (D-063). Вызывать в транзакции создания."""
    users = (await db.scalars(_participants(contest.id))).all()
    letters = [(user, *invitation_text(contest, user)) for user in users]
    return await JobRunner._send(db, contest, EmailKind.INVITATION, letters, now)


async def _creator(db: AsyncSession, contest: Contest) -> User | None:
    """Создатель конкурса — получатель писем организатора, если он всё ещё организатор с доступом."""
    user = await db.get(User, contest.created_by)
    return user if user is not None and user.is_active and user.role == Role.ORGANIZER else None


async def _notify_organizer(
    db: AsyncSession, contest: Contest, kind: EmailKind, facts: dict, now: datetime
) -> list[int]:
    organizer = await _creator(db, contest)
    if organizer is None:
        return []
    return await JobRunner._send(db, contest, kind, [(organizer, *_organizer_text(kind, contest, organizer, facts))], now)


async def _count(db: AsyncSession, statement) -> int:
    return await db.scalar(statement) or 0


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
        notified: list[int] = []
        if job.attempts >= MAX_ATTEMPTS:
            job.status = JobStatus.FAILED
            job.finished_at = now
            # Организатор узнаёт о сбое письмом, а не только если сам откроет конкурс (D-063).
            # Письмо — в своей точке сохранения: его сбой не мешает записать статус задания.
            try:
                async with db.begin_nested():
                    contest = await db.get(Contest, job.contest_id)
                    notified = await _notify_organizer(
                        db, contest, EmailKind.ORG_JOB_FAILED, {"job": job.kind}, now
                    )
            except Exception:  # noqa: BLE001
                log.exception("Не удалось записать письмо о сбое задания %s", job.id)
                notified = []
        else:
            job.run_at = now + RETRY_STEP * job.attempts
        await db.commit()
        self._hub.schedule_changed(job.contest_id)
        self._hub.mail_changed(notified)
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

        participants_count = await _count(
            db, select(func.count()).where(ContestParticipant.contest_id == contest.id)
        )
        ideas_count = await _count(db, select(func.count()).select_from(Idea).where(Idea.contest_id == contest.id))

        if kind == JobKind.FINALIZE:
            if phase != Phase.FINISHED:
                raise RuntimeError("финал запущен до срока голосования")
            ranking = await ranked_ideas(db, contest.id)
            users = (await db.scalars(_participants(contest.id))).all()
            letters = [(user, *_final_text(contest, user, ranking)) for user in users]
            sent = await JobRunner._send(db, contest, EmailKind.FINAL, letters, now)
            organizer = await _creator(db, contest)
            to_organizer = (
                await JobRunner._send(db, contest, EmailKind.FINAL, [(organizer, *_final_text(contest, organizer, ranking))], now)
                if organizer is not None
                else []
            )
            winner = f"победитель — идея {ranking[0].id}" if ranking else "идей нет"
            return JobStatus.DONE, f"писем: {len(sent)}; {winner}", sent + to_organizer

        if kind == JobKind.OPEN_VOTING:
            # Голосование уже закончилось (сервер долго не работал) — сообщать о начале поздно.
            if phase != Phase.VOTING:
                return JobStatus.SKIPPED, "голосование уже завершилось", []
            sent = []
            if ideas_count:
                # Всем участникам, а не «тем, у кого есть чужие идеи»: иначе в журнале рассылки по
                # тому, кому письмо не пришло, был бы виден автор (приёмка версии 2, D-058).
                users = (await db.scalars(_participants(contest.id))).all()
                letters = [(user, *_voting_open_text(contest, user, ideas_count)) for user in users]
                sent = await JobRunner._send(db, contest, EmailKind.VOTING_OPEN, letters, now)
            to_organizer = await _notify_organizer(
                db, contest, EmailKind.ORG_SUBMISSION_CLOSED, {"ideas": ideas_count}, now
            )
            note = f"писем: {len(sent)}" if ideas_count else "идей нет — голосовать не за что"
            return JobStatus.DONE, note, sent + to_organizer

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
        # Организатору — сводка числами: те же числа он видит в статистике и расписании (D-058, D-063).
        facts = {"participants": participants_count, "ideas": ideas_count, "reminded": len(sent)}
        if kind == JobKind.REMIND_SUBMISSION:
            to_organizer = await _notify_organizer(db, contest, EmailKind.ORG_SUBMISSION_SOON, facts, now)
        else:
            facts["voters"] = await _count(
                db, select(func.count(func.distinct(Vote.voter_id))).where(Vote.contest_id == contest.id)
            )
            to_organizer = await _notify_organizer(db, contest, EmailKind.ORG_VOTING_SOON, facts, now)
        return JobStatus.DONE, f"писем: {len(sent)}", sent + to_organizer

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
