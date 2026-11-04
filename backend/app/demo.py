"""Демонстрационные конкурсы во всех трёх фазах (D-054).

Создаются:
- автоматически при старте backend, если конкурсов ещё нет (`python -m app.seed`);
- вручную в любой момент: `python -m app.demo` добавляет свежий набор, ничего не удаляя.

Сроки отсчитываются от текущего момента, поэтому сразу после создания конкурсы находятся
в нужных фазах. История «проигрывается» по времени: идеи, голоса и задания расписания
применяются в хронологическом порядке, а письма пишет тот же код, что и в работе
(`JobRunner.execute`). Напоминания получают ровно те, кому их отправил бы сервис.

Все данные синтетические.
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock, SystemClock
from app.config import Settings
from app.db import create_engine, create_sessionmaker
from app.jobs import JobRunner, plan_jobs
from app.models import Contest, ContestParticipant, Idea, Job, JobStatus, Role, User, Vote


def at(days: float = 0, hours: float = 0, minutes: float = 0, seconds: float = 0) -> timedelta:
    """Смещение от «якоря» — начала текущего часа. Отрицательное — в прошлом."""
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


@dataclass(frozen=True)
class DemoIdea:
    key: str
    author: str  # логин
    title: str
    description: str
    submitted: timedelta


@dataclass(frozen=True)
class DemoVote:
    voter: str  # логин
    idea: str  # ключ идеи
    cast: timedelta


@dataclass(frozen=True)
class DemoContest:
    topic: str
    participants: tuple[str, ...]
    created: timedelta
    submission_deadline: timedelta
    voting_deadline: timedelta
    ideas: tuple[DemoIdea, ...] = ()
    votes: tuple[DemoVote, ...] = ()


# Что показывает каждый конкурс — docs/DECISIONS.md, D-054; сценарий показа — README.
DEMO_CONTESTS: tuple[DemoContest, ...] = (
    # Завершён. Ничья 2:2 за первое место: победила идея Бориса — она подана на 27 секунд
    # раньше идеи Веры. Дина не участвует и конкурса не видит.
    DemoContest(
        topic="Как сделать обеды в офисе удобнее",
        participants=("anna", "boris", "vera", "gleb"),
        created=at(days=-10),
        submission_deadline=at(days=-6),
        voting_deadline=at(days=-3),
        ideas=(
            DemoIdea(
                "chatbot",
                "boris",
                "Предзаказ обедов через чат-бот",
                "Бот в рабочем мессенджере принимает заказы до 11:00 и передаёт их столовой "
                "одним списком. Меньше очередей, меньше остатков.",
                at(days=-8, minutes=15, seconds=20),
            ),
            DemoIdea(
                "microwaves",
                "vera",
                "Микроволновки на каждом этаже",
                "Сейчас одна кухня на три этажа, и в обед к ней очередь. "
                "По две микроволновки на этаж решат проблему.",
                at(days=-8, minutes=15, seconds=47),
            ),
            DemoIdea(
                "terrace",
                "anna",
                "Общий стол на летней террасе",
                "Длинный стол под навесом: можно обедать на воздухе и знакомиться "
                "с коллегами из других отделов.",
                at(days=-7, hours=4),
            ),
            DemoIdea(
                "fruit",
                "anna",
                "Фруктовый день по пятницам",
                "Корзина сезонных фруктов на кухне каждую пятницу.",
                at(days=-7, hours=6),
            ),
        ),
        votes=(
            DemoVote("anna", "chatbot", at(days=-5, hours=-3)),
            DemoVote("anna", "microwaves", at(days=-5, hours=-3, minutes=1)),
            DemoVote("boris", "microwaves", at(days=-5)),
            DemoVote("vera", "terrace", at(days=-4, hours=-6)),
            DemoVote("gleb", "chatbot", at(days=-3, hours=-5)),
        ),
    ),
    # Голосование. Идеи видны всем участникам без авторов; Анна ещё не голосовала —
    # за неё удобно показать голос и отзыв. Дина идей не подавала.
    DemoContest(
        topic="Как сократить время на совещания",
        participants=("anna", "boris", "vera", "gleb", "dina"),
        created=at(days=-4),
        submission_deadline=at(hours=-20),
        voting_deadline=at(days=2),
        ideas=(
            DemoIdea(
                "standing",
                "anna",
                "Совещания стоя — не дольше 15 минут",
                "Короткие ежедневные встречи без стульев: обсуждаем только блокеры, "
                "остальное — в чате.",
                at(days=-3, hours=2),
            ),
            DemoIdea(
                "agenda",
                "boris",
                "Повестка за день до встречи",
                "Без повестки встреча не назначается. Участники заранее знают, зачем идут, "
                "и могут отказаться.",
                at(days=-3, hours=5),
            ),
            DemoIdea(
                "no-meetings",
                "vera",
                "Среда без совещаний",
                "Один день в неделю целиком для сосредоточенной работы.",
                at(days=-2, hours=-3),
            ),
            DemoIdea(
                "written",
                "gleb",
                "Письменные статусы вместо планёрок",
                "Каждый участник команды утром пишет в общий канал три строки: что сделано, "
                "что в планах и что мешает.",
                at(hours=-22),
            ),
        ),
        votes=(
            DemoVote("boris", "no-meetings", at(hours=-18)),
            DemoVote("gleb", "no-meetings", at(hours=-15)),
            DemoVote("vera", "agenda", at(hours=-12)),
            DemoVote("dina", "standing", at(hours=-6)),
        ),
    ),
    # Приём идей. Каждый участник видит только свои идеи, организатор — только их число.
    # Вера и Глеб ещё ничего не подали — им придёт напоминание.
    DemoContest(
        topic="Как сделать офис уютнее",
        participants=("anna", "boris", "vera", "gleb"),
        created=at(days=-1),
        submission_deadline=at(days=2),
        voting_deadline=at(days=4),
        ideas=(
            DemoIdea(
                "plants",
                "anna",
                "Живые растения в опенспейсе",
                "Крупные растения в кадках между рядами столов: меньше шума и приятнее глазу.",
                at(hours=-20),
            ),
            DemoIdea(
                "quiet-room",
                "anna",
                "Тихая комната для звонков",
                "Небольшая переговорная без бронирования — для звонков до 15 минут.",
                at(hours=-5),
            ),
            DemoIdea(
                "blankets",
                "boris",
                "Пледы и мягкие кресла в зоне отдыха",
                "Пара кресел и пледы у окна — место, где можно спокойно выпить кофе.",
                at(hours=-3),
            ),
        ),
    ),
)


async def create_demo_contests(db: AsyncSession, clock: Clock, reminder_lead: timedelta) -> list[int]:
    """Создаёт демо-конкурсы с историей; возвращает их номера. Фиксирует транзакцию."""
    now = clock.now()
    anchor = now.replace(minute=0, second=0, microsecond=0)
    users = {u.login: u for u in (await db.scalars(select(User))).all()}
    organizer = next((u for u in users.values() if u.role == Role.ORGANIZER), None)
    if organizer is None:
        raise RuntimeError("Нет демо-пользователей: сначала выполните python -m app.seed")

    created = []
    for spec in DEMO_CONTESTS:
        contest = await _create_contest(db, spec, anchor, now, organizer, users, reminder_lead)
        created.append(contest.id)
    await db.commit()
    return created


async def _create_contest(
    db: AsyncSession,
    spec: DemoContest,
    anchor: datetime,
    now: datetime,
    organizer: User,
    users: dict[str, User],
    lead: timedelta,
) -> Contest:
    created_at = anchor + spec.created
    contest = Contest(
        topic=spec.topic,
        submission_deadline=anchor + spec.submission_deadline,
        voting_deadline=anchor + spec.voting_deadline,
        created_by=organizer.id,
        created_at=created_at,
        client_request_id=uuid.uuid4(),
        revision=1,
    )
    db.add(contest)
    await db.flush()
    db.add_all(ContestParticipant(contest_id=contest.id, user_id=users[login].id) for login in spec.participants)
    jobs = [
        Job(**row)
        for row in plan_jobs(
            contest.id,
            created_at=created_at,
            submission_deadline=contest.submission_deadline,
            voting_deadline=contest.voting_deadline,
            lead=lead,
        )
    ]
    db.add_all(jobs)
    await db.flush()

    # Хронология: идеи, голоса и наступившие задания — в том порядке, в каком они случились бы.
    events: list[tuple[datetime, int, object]] = []
    events += [(anchor + idea.submitted, 0, idea) for idea in spec.ideas]
    events += [(anchor + vote.cast, 0, vote) for vote in spec.votes]
    events += [(job.run_at, 1, job) for job in jobs if job.status == JobStatus.PENDING and job.run_at <= now]
    events.sort(key=lambda event: (event[0], event[1]))

    ideas: dict[str, Idea] = {}
    for moment, _, item in events:
        if isinstance(item, DemoIdea):
            idea = Idea(
                contest_id=contest.id,
                author_id=users[item.author].id,
                title=item.title,
                description=item.description,
                submitted_at=moment,
                updated_at=moment,
                version=1,
                client_request_id=uuid.uuid4(),
            )
            db.add(idea)
            ideas[item.key] = idea
            contest.revision += 1
        elif isinstance(item, DemoVote):
            db.add(Vote(idea_id=ideas[item.idea].id, voter_id=users[item.voter].id, contest_id=contest.id, created_at=moment))
            contest.revision += 1
        else:
            status, note, _ = await JobRunner.execute(db, item, contest, moment)
            item.status, item.note, item.finished_at = status, note, moment
        await db.flush()
    return contest


async def has_contests(db: AsyncSession) -> bool:
    return bool(await db.scalar(select(func.count()).select_from(Contest)))


async def _main() -> None:
    settings = Settings()
    engine = create_engine(settings.database_url)
    try:
        async with create_sessionmaker(engine)() as db:
            ids = await create_demo_contests(db, SystemClock(), settings.reminder_lead)
        print(f"demo: созданы демо-конкурсы {ids} (приём идей, голосование, завершён)")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
