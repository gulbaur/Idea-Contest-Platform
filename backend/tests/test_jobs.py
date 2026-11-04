"""Расписание, напоминания, финал, письма (F7, F9, F17, P5, P6; D-042 … D-046).

Время — управляемые часы: «сутки до срока» проверяются без ожидания. Обработчик
вызывается напрямую (`run_due`), а фоновый цикл — отдельными тестами в конце.
"""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from app.jobs import JobRunner, _votes, _when
from app.main import create_app
from app.models import Email, Job
from tests.helpers import (
    T0,
    auth,
    create_contest,
    login,
    revoke,
    snapshot,
    submit_idea,
    vote,
)

pytestmark = pytest.mark.usefixtures("demo_users")

DAY = timedelta(days=1)
TICK = timedelta(microseconds=1)
# Конкурс длиннее суток в каждом раунде: напоминания «за сутки» успевают.
SUB_END = T0 + 2 * DAY
VOTE_END = T0 + 4 * DAY
REMIND_SUB = SUB_END - DAY
REMIND_VOTE = VOTE_END - DAY
PARTICIPANTS = ("anna", "boris", "vera", "gleb")


@pytest.fixture
async def t(client, app) -> dict[str, str]:
    # Часы в этих тестах уходят на дни вперёд — сессии входа должны пережить конкурс.
    app.state.settings.session_ttl_hours = 24 * 30
    return {u: await login(client, u) for u in ("organizer", *PARTICIPANTS, "dina")}


@pytest.fixture
async def cid(client, t, user_ids) -> int:
    contest = await create_contest(
        client,
        t["organizer"],
        submission_deadline=SUB_END,
        voting_deadline=VOTE_END,
        participants=[user_ids[u] for u in PARTICIPANTS],
    )
    return contest["id"]


async def jobs_of(app, contest_id: int) -> dict[str, Job]:
    async with app.state.sessionmaker() as db:
        rows = await db.scalars(select(Job).where(Job.contest_id == contest_id))
        return {job.kind: job for job in rows}


async def emails(app, **filters) -> list[Email]:
    statement = select(Email).order_by(Email.recipient_id, Email.kind)
    for column, value in filters.items():
        statement = statement.where(getattr(Email, column) == value)
    async with app.state.sessionmaker() as db:
        return list((await db.scalars(statement)).all())


def recipients(letters, user_ids) -> set[str]:
    names = {v: k for k, v in user_ids.items()}
    return {names[letter.recipient_id] for letter in letters}


async def idea(client, token, contest_id, title="Идея") -> int:
    response = await submit_idea(client, token, contest_id, title)
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- план заданий ------------------------------------------------------------


async def test_contest_gets_three_jobs_at_the_right_moments(app, cid):
    jobs = await jobs_of(app, cid)
    assert {k: (j.run_at, j.status) for k, j in jobs.items()} == {
        "remind_submission": (REMIND_SUB, "pending"),
        "remind_voting": (REMIND_VOTE, "pending"),
        "finalize": (VOTE_END, "pending"),
    }


async def test_rounds_shorter_than_lead_skip_their_reminders_at_creation(client, app, t):
    """Конкурс короче суток (D-042): напоминать «за сутки» поздно — сразу skipped."""
    short = await create_contest(client, t["organizer"])  # раунды по 1 часу
    mixed = await create_contest(
        client, t["organizer"], submission_deadline=SUB_END, voting_deadline=SUB_END + timedelta(hours=3)
    )

    jobs = await jobs_of(app, short["id"])
    assert jobs["remind_submission"].status == jobs["remind_voting"].status == "skipped"
    assert jobs["remind_submission"].note == "раунд короче срока напоминания"
    assert jobs["finalize"].status == "pending"
    jobs = await jobs_of(app, mixed["id"])
    assert (jobs["remind_submission"].status, jobs["remind_voting"].status) == ("pending", "skipped")


async def test_reminder_exactly_at_round_start_is_kept(client, app, t, clock):
    contest = await create_contest(
        client, t["organizer"], submission_deadline=clock.now() + DAY, voting_deadline=VOTE_END
    )
    jobs = await jobs_of(app, contest["id"])
    assert (jobs["remind_submission"].run_at, jobs["remind_submission"].status) == (clock.now(), "pending")


async def test_reminder_lead_comes_from_settings(client, app, t):
    app.state.settings.reminder_lead = timedelta(minutes=2)  # как REMINDER_LEAD=00:02:00
    contest = await create_contest(client, t["organizer"])
    jobs = await jobs_of(app, contest["id"])
    assert jobs["remind_submission"].run_at == T0 + timedelta(hours=1) - timedelta(minutes=2)
    assert jobs["remind_voting"].run_at == T0 + timedelta(hours=2) - timedelta(minutes=2)
    assert {j.status for j in jobs.values()} == {"pending"}


async def test_nothing_runs_before_its_moment(app, cid, clock):
    clock.set(REMIND_SUB - TICK)
    assert await app.state.jobs.run_due() == []
    assert await emails(app) == []


# --- напоминание о подаче ----------------------------------------------------


async def test_submission_reminder_goes_only_to_participants_without_ideas(
    client, app, t, cid, clock, user_ids
):
    await idea(client, t["anna"], cid)
    boris_idea = await idea(client, t["boris"], cid)
    # Удалил все свои идеи — снова «не участвовал» (D-010).
    assert (await client.delete(f"/api/ideas/{boris_idea}", headers=auth(t["boris"]))).status_code == 204

    clock.set(REMIND_SUB)
    [outcome] = await app.state.jobs.run_due()

    assert (outcome.kind, outcome.status, outcome.note) == ("remind_submission", "done", "писем: 3")
    letters = await emails(app, kind="reminder_submission")
    # Не anna (подала), не организатор, не dina (не в списке участников).
    assert recipients(letters, user_ids) == {"boris", "vera", "gleb"}
    vera = next(e for e in letters if e.recipient_id == user_ids["vera"])
    assert vera.to_address == "vera@example.com"
    assert vera.subject == "Напоминание: приём идей закрывается 17.01.2026 09:00 UTC"
    assert "Вера Орлова" in vera.body and "Как улучшить офис" in vera.body


async def test_reminder_is_sent_once_even_if_job_runs_again(client, app, t, cid, clock, user_ids):
    clock.set(REMIND_SUB)
    await app.state.jobs.run_due()
    assert len(await emails(app)) == 4
    assert await app.state.jobs.run_due() == []  # выполненное задание не повторяется

    # Даже если задание по ошибке снова «pending», второго письма не будет (UNIQUE, D-012).
    async with app.state.sessionmaker() as db:
        await db.execute(update(Job).where(Job.contest_id == cid).values(status="pending"))
        await db.commit()
    clock.set(REMIND_SUB + timedelta(minutes=1))
    outcomes = await app.state.jobs.run_due()
    assert [o.note for o in outcomes if o.kind == "remind_submission"] == ["писем: 0"]
    assert len(await emails(app)) == 4


async def test_database_itself_rejects_second_letter_of_same_kind(app, cid, clock, user_ids):
    clock.set(REMIND_SUB)
    await app.state.jobs.run_due()
    async with app.state.sessionmaker() as db:
        with pytest.raises(IntegrityError, match="uq_emails_contest_id_recipient_id_kind"):
            await db.execute(
                text(
                    "INSERT INTO emails (contest_id, recipient_id, to_address, kind, subject, body, created_at) "
                    "SELECT contest_id, recipient_id, to_address, kind, subject, body, created_at FROM emails LIMIT 1"
                )
            )


# --- напоминание о голосовании -----------------------------------------------


async def test_voting_reminder_goes_to_participants_without_current_votes(
    client, app, t, cid, clock, user_ids
):
    a = await idea(client, t["anna"], cid, "A")
    b = await idea(client, t["boris"], cid, "B")
    c = await idea(client, t["vera"], cid, "C")
    clock.set(SUB_END)
    assert (await vote(client, t["vera"], a)).status_code == 201  # проголосовала
    assert (await vote(client, t["boris"], a)).status_code == 201  # boris — за чужую A
    assert (await vote(client, t["gleb"], b)).status_code == 201
    assert (await revoke(client, t["gleb"], b)).status_code == 204  # отозвал все — «не участвовал»
    assert (await vote(client, t["anna"], c)).status_code == 201
    # Голос anna исчез вместе с удалённой идеей C — тоже «не участвовала» (D-010).
    assert (await client.delete(f"/api/ideas/{c}", headers=auth(t["vera"]))).status_code == 204

    clock.set(REMIND_VOTE)
    outcomes = {o.kind: o for o in await app.state.jobs.run_due()}

    # Напоминание о подаче часы «проскочили» — подача уже закрыта, оно пропущено.
    assert outcomes["remind_submission"].status == "skipped"
    assert outcomes["remind_voting"].status == "done"
    letters = await emails(app, kind="reminder_voting")
    assert recipients(letters, user_ids) == {"gleb", "anna"}
    assert letters[0].subject == "Напоминание: голосование закрывается 19.01.2026 09:00 UTC"


async def test_voting_reminder_skips_participant_with_nothing_to_vote_for(
    client, app, t, cid, clock, user_ids
):
    """Единственные идеи конкурса — свои: голосовать не за что, напоминание не нужно (D-044)."""
    await idea(client, t["anna"], cid, "A1")
    await idea(client, t["anna"], cid, "A2")
    clock.set(REMIND_VOTE)
    await app.state.jobs.run_due()
    assert recipients(await emails(app, kind="reminder_voting"), user_ids) == {"boris", "vera", "gleb"}


async def test_voting_reminder_is_skipped_when_there_are_no_ideas(app, cid, clock):
    clock.set(REMIND_VOTE)
    outcomes = {o.kind: o for o in await app.state.jobs.run_due()}
    assert (outcomes["remind_voting"].status, outcomes["remind_voting"].note) == (
        "skipped",
        "идей нет — голосовать не за что",
    )
    assert await emails(app, kind="reminder_voting") == []


# --- простой сервера ---------------------------------------------------------


async def test_downtime_skips_reminders_of_closed_rounds_and_runs_late_final(
    client, app, t, cid, clock, user_ids
):
    """Сервер «лежал» во время напоминаний и сроков (D-015, D-043)."""
    await idea(client, t["anna"], cid)
    clock.set(SUB_END + timedelta(hours=1))  # напоминание о подаче проспано, подача закрыта
    [outcome] = await app.state.jobs.run_due()
    assert (outcome.kind, outcome.status, outcome.note) == ("remind_submission", "skipped", "раунд уже закрыт")

    clock.set(VOTE_END + timedelta(hours=5))  # проспаны и напоминание о голосовании, и финал
    outcomes = {o.kind: o for o in await app.state.jobs.run_due()}
    assert outcomes["remind_voting"].status == "skipped"
    assert outcomes["finalize"].status == "done"  # финал — с опозданием, но выполнен
    assert await emails(app, kind="reminder_submission") == []
    assert await emails(app, kind="reminder_voting") == []
    assert recipients(await emails(app, kind="final"), user_ids) == set(PARTICIPANTS)


async def test_overdue_reminder_is_still_sent_while_round_is_open(client, app, t, cid, clock, user_ids):
    clock.set(REMIND_SUB + timedelta(hours=3))  # опоздали, но приём идей ещё идёт
    [outcome] = await app.state.jobs.run_due()
    assert outcome.status == "done"
    assert recipients(await emails(app), user_ids) == set(PARTICIPANTS)


# --- финал -------------------------------------------------------------------


async def test_final_letter_once_per_participant_winner_gets_winner_variant(
    client, app, t, cid, clock, user_ids
):
    a = await idea(client, t["anna"], cid, "Велопарковка")
    b = await idea(client, t["boris"], cid, "Тихая комната")
    await idea(client, t["boris"], cid, "Кофемашина")
    clock.set(SUB_END)
    for who, target in (("vera", b), ("gleb", b), ("anna", b), ("gleb", a)):
        assert (await vote(client, t[who], target)).status_code == 201
    clock.set(VOTE_END)

    outcomes = {o.kind: o for o in await app.state.jobs.run_due()}
    assert outcomes["finalize"].status == "done"
    assert outcomes["finalize"].note == f"писем: 4; победитель — идея {b}"

    finals = await emails(app, kind="final")
    # Ровно одно письмо каждому участнику; организатору и dina — нет (D-012, D-044).
    assert sorted(recipients(finals, user_ids)) == sorted(PARTICIPANTS)
    assert len(finals) == 4
    names = {v: k for k, v in user_ids.items()}
    by_name = {names[e.recipient_id]: e for e in finals}
    assert by_name["boris"].subject == "Ваша идея победила в конкурсе «Как улучшить офис»"
    assert "Поздравляем" in by_name["boris"].body
    assert by_name["vera"].subject == "Итоги конкурса «Как улучшить офис»"
    assert (
        "1. Тихая комната — 3 голоса — автор: Борис Котов\n"
        "2. Велопарковка — 1 голос — автор: Анна Смирнова\n"
        "3. Кофемашина — 0 голосов — автор: Борис Котов" in by_name["vera"].body
    )
    assert "При равенстве голосов побеждает идея, поданная раньше." in by_name["vera"].body
    # Письмо и снимок объявляют одного победителя.
    assert (await snapshot(client, t["vera"], cid)).json()["winner_idea_id"] == b


async def test_final_without_votes_earliest_idea_wins(client, app, t, cid, clock, user_ids):
    await idea(client, t["vera"], cid, "Ранняя")
    clock.advance(timedelta(minutes=1))
    await idea(client, t["anna"], cid, "Поздняя")
    clock.set(VOTE_END)
    await app.state.jobs.run_due()
    vera = (await emails(app, kind="final", recipient_id=user_ids["vera"]))[0]
    assert vera.subject.startswith("Ваша идея победила")


async def test_final_without_ideas_tells_everyone_there_is_no_winner(app, cid, clock, user_ids):
    clock.set(VOTE_END)
    await app.state.jobs.run_due()
    finals = await emails(app, kind="final")
    assert recipients(finals, user_ids) == set(PARTICIPANTS)
    assert all("Идей не подано, победителя нет." in e.body for e in finals)


async def test_final_waits_for_vote_accepted_just_before_deadline(client, app, t, cid, clock, user_ids):
    """Голос, проверенный до срока, но ещё не зафиксированный, попадает в итог (REVIEW В2)."""
    a = await idea(client, t["anna"], cid, "A")
    b = await idea(client, t["boris"], cid, "B")
    clock.set(VOTE_END)
    async with app.state.engine.connect() as other:  # «запрос голосования» в своём соединении
        transaction = await other.begin()
        await other.execute(text("SELECT id FROM contests WHERE id = :c FOR UPDATE"), {"c": cid})
        await other.execute(
            text("INSERT INTO votes (idea_id, voter_id, contest_id, created_at) VALUES (:i, :v, :c, :t)"),
            {"i": b, "v": user_ids["vera"], "c": cid, "t": VOTE_END - TICK},
        )
        final = asyncio.create_task(app.state.jobs.run_due())
        await asyncio.sleep(0.3)
        assert not final.done()  # финал ждёт блокировку конкурса
        await transaction.commit()
    await final

    # Без ожидания победила бы A (поданная раньше при 0 : 0); с голосом — B.
    boris = (await emails(app, kind="final", recipient_id=user_ids["boris"]))[0]
    assert boris.subject.startswith("Ваша идея победила")
    assert f"победитель — идея {b}" in (await jobs_of(app, cid))["finalize"].note


# --- перезапуск и несколько обработчиков -------------------------------------


async def test_after_restart_jobs_continue_and_done_ones_are_not_repeated(
    client, app, settings, t, cid, clock, user_ids
):
    clock.set(REMIND_SUB)
    await app.state.jobs.run_due()
    assert len(await emails(app, kind="reminder_submission")) == 4

    # «Перезапуск»: новое приложение — новый пул соединений и новый обработчик; БД та же.
    restarted = create_app(settings=settings, clock=clock)
    try:
        assert await restarted.state.jobs.run_due() == []  # выполненное — не повторяется
        clock.set(REMIND_VOTE)
        restarted.state.jobs.start()  # фоновый цикл нового процесса сам подхватывает задания
        for _ in range(100):
            if (await jobs_of(app, cid))["remind_voting"].status != "pending":
                break
            await asyncio.sleep(0.02)
        await restarted.state.jobs.stop()
        assert (await jobs_of(app, cid))["remind_voting"].status == "skipped"  # идей нет
        clock.set(VOTE_END)
        assert [o.kind for o in await restarted.state.jobs.run_due()] == ["finalize"]
    finally:
        await restarted.state.jobs.stop()
        await restarted.state.engine.dispose()
    assert len(await emails(app, kind="reminder_submission")) == 4
    assert len(await emails(app, kind="final")) == 4


async def test_two_runners_in_parallel_execute_each_job_once(client, app, settings, t, clock, user_ids):
    contests = [
        (
            await create_contest(
                client,
                t["organizer"],
                topic=f"Конкурс {n}",
                submission_deadline=SUB_END,
                voting_deadline=VOTE_END,
                participants=[user_ids[u] for u in PARTICIPANTS],
            )
        )["id"]
        for n in range(6)
    ]
    second = create_app(settings=settings, clock=clock)  # другой процесс, свои соединения
    try:
        clock.set(REMIND_SUB)
        first_done, second_done = await asyncio.gather(
            app.state.jobs.run_due(), second.state.jobs.run_due()
        )
    finally:
        await second.state.engine.dispose()

    done_ids = [o.job_id for o in first_done + second_done]
    assert len(done_ids) == len(set(done_ids)) == len(contests)  # каждое задание — один раз
    assert len(await emails(app)) == len(contests) * len(PARTICIPANTS)  # и без лишних писем


# --- ошибки ------------------------------------------------------------------


async def test_failed_job_rolls_back_its_letters_and_is_retried(app, cid, clock, monkeypatch):
    original = JobRunner._send
    calls = 0

    async def send_then_fail(db, *args):
        nonlocal calls
        calls += 1
        sent = await original(db, *args)
        if calls == 1:
            raise RuntimeError("сбой после записи писем")
        return sent

    monkeypatch.setattr(JobRunner, "_send", staticmethod(send_then_fail))
    clock.set(REMIND_SUB)
    [failed] = await app.state.jobs.run_due()

    job = (await jobs_of(app, cid))["remind_submission"]
    assert (job.status, job.attempts) == ("pending", 1)
    assert job.last_error == "RuntimeError: сбой после записи писем"
    assert job.run_at == REMIND_SUB + timedelta(seconds=5)
    assert await emails(app) == []  # письма откатились вместе с ошибкой

    assert await app.state.jobs.run_due() == []  # повтор — не раньше назначенного
    clock.advance(timedelta(seconds=5))
    [retried] = await app.state.jobs.run_due()
    assert retried.status == "done"
    assert len(await emails(app)) == 4


async def test_job_failing_five_times_is_marked_failed(app, cid, clock, monkeypatch):
    async def always_fail(*args):
        raise RuntimeError("постоянный сбой")

    monkeypatch.setattr(JobRunner, "execute", staticmethod(always_fail))
    clock.set(REMIND_SUB)
    for _ in range(5):
        await app.state.jobs.run_due()
        clock.advance(timedelta(minutes=1))
    job = (await jobs_of(app, cid))["remind_submission"]
    assert (job.status, job.attempts) == ("failed", 5)
    assert await app.state.jobs.run_due() == []  # больше не пытается


# --- API почты ---------------------------------------------------------------


async def test_participant_sees_only_own_letters_organizer_sees_all(client, app, t, cid, clock, user_ids):
    await idea(client, t["anna"], cid)
    clock.set(REMIND_SUB)
    await app.state.jobs.run_due()

    vera = (await client.get("/api/emails", headers=auth(t["vera"]))).json()
    assert [(e["recipient"]["id"], e["kind"]) for e in vera] == [(user_ids["vera"], "reminder_submission")]
    assert vera[0]["contest_topic"] == "Как улучшить офис"
    assert set(vera[0]) == {
        "id", "contest_id", "contest_topic", "recipient", "to_address", "kind", "subject", "body", "created_at",
    }
    assert (await client.get("/api/emails", headers=auth(t["anna"]))).json() == []  # подала идею
    assert (await client.get("/api/emails", headers=auth(t["dina"]))).json() == []

    journal = (await client.get("/api/emails", headers=auth(t["organizer"]))).json()
    assert {e["recipient"]["id"] for e in journal} == {user_ids[u] for u in ("boris", "vera", "gleb")}
    filtered = await client.get("/api/emails", params={"contest_id": cid + 1}, headers=auth(t["organizer"]))
    assert filtered.json() == []
    assert (await client.get("/api/emails")).status_code == 401


async def test_letters_are_listed_newest_first(client, app, t, cid, clock):
    clock.set(REMIND_SUB)
    await app.state.jobs.run_due()
    clock.set(VOTE_END)
    await app.state.jobs.run_due()
    kinds = [e["kind"] for e in (await client.get("/api/emails", headers=auth(t["vera"]))).json()]
    assert kinds == ["final", "reminder_submission"]


# --- сигнал WebSocket --------------------------------------------------------


async def test_mail_signal_goes_to_recipients_and_organizers(client, app, t, cid, clock, open_tab):
    await idea(client, t["anna"], cid)
    org, vera, anna = await open_tab(t["organizer"]), await open_tab(t["vera"]), await open_tab(t["anna"])
    clock.set(REMIND_SUB)
    await app.state.jobs.run_due()

    assert await org.next() == {"type": "mail_changed"}
    assert await vera.next() == {"type": "mail_changed"}
    await anna.expect_nothing()  # ей письма не было


# --- фоновый цикл ------------------------------------------------------------


async def test_background_runner_sends_reminder_when_clock_reaches_it(app, cid, clock):
    app.state.jobs.start()
    try:
        clock.set(REMIND_SUB)
        for _ in range(100):
            if await emails(app):
                break
            await asyncio.sleep(0.02)
        assert len(await emails(app)) == 4
    finally:
        await app.state.jobs.stop()


async def test_background_runner_wakes_up_for_new_contest(client, app, t, clock, user_ids):
    """Обработчик спит до 60 с; создание конкурса будит его, и он ждёт уже до нового задания."""
    runner = JobRunner(app.state.sessionmaker, clock, app.state.hub, max_sleep_seconds=60)
    app.state.settings.reminder_lead = timedelta(milliseconds=300)
    runner.start()
    try:
        await asyncio.sleep(0.05)  # заданий нет — уснул на 60 с
        await create_contest(
            client,
            t["organizer"],
            submission_deadline=clock.now() + timedelta(milliseconds=600),
            voting_deadline=clock.now() + timedelta(hours=1),
            participants=[user_ids["anna"]],
        )
        clock.advance(timedelta(milliseconds=300))
        for _ in range(150):
            if await emails(app):
                break
            await asyncio.sleep(0.02)
        assert [e.recipient_id for e in await emails(app)] == [user_ids["anna"]]
    finally:
        await runner.stop()


# --- тексты ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "text"),
    [(0, "0 голосов"), (1, "1 голос"), (2, "2 голоса"), (5, "5 голосов"), (11, "11 голосов"),
     (21, "21 голос"), (22, "22 голоса"), (112, "112 голосов")],
)
def test_vote_count_is_spelled_correctly(n, text):
    assert _votes(n) == text


def test_letter_time_is_utc_with_label():
    from datetime import UTC, datetime, timezone

    moment = datetime(2026, 1, 17, 14, 30, tzinfo=timezone(timedelta(hours=5)))
    assert _when(moment) == "17.01.2026 09:30 UTC"
    assert _when(datetime(2026, 1, 17, 9, 30, tzinfo=UTC)) == "17.01.2026 09:30 UTC"


# --- экран организатора: участники и расписание (D-051) ----------------------


async def test_organizer_snapshot_shows_participants_and_schedule(client, app, t, cid, clock):
    participants = await client.get(f"/api/contests/{cid}/participants", headers=auth(t["organizer"]))
    assert [p["display_name"] for p in participants.json()] == [
        "Анна Смирнова", "Борис Котов", "Вера Орлова", "Глеб Лебедев",
    ]
    snap = (await snapshot(client, t["organizer"], cid)).json()
    assert [(j["kind"], j["status"]) for j in snap["schedule"]] == [
        ("remind_submission", "pending"), ("remind_voting", "pending"), ("finalize", "pending"),
    ]

    clock.set(REMIND_SUB)
    await app.state.jobs.run_due()
    item = (await snapshot(client, t["organizer"], cid)).json()["schedule"][0]
    assert (item["status"], item["note"], item["finished_at"] is not None) == ("done", "писем: 4", True)

    # Участникам — ни списка участников, ни расписания.
    assert (await snapshot(client, t["anna"], cid)).json()["schedule"] is None
    response = await client.get(f"/api/contests/{cid}/participants", headers=auth(t["anna"]))
    assert response.status_code == 403


async def test_schedule_signal_goes_only_to_organizers(client, app, t, cid, clock, open_tab):
    await idea(client, t["anna"], cid)
    org, anna = await open_tab(t["organizer"]), await open_tab(t["anna"])
    clock.set(REMIND_VOTE)  # оба напоминания выполняются: о подаче — пропущено, о голосовании — отправлено
    await app.state.jobs.run_due()

    received = []
    await org.ws.send('{"type": "ping"}')
    while (message := await org.next()) != {"type": "pong"}:
        received.append(message)
    assert {"type": "schedule_changed", "contest_id": cid} in received
    await anna.expect_nothing()  # anna — автор единственной идеи: писем и сигналов ей нет
