"""Уведомления (D-063): приглашения, «голосование открыто», письма организатору, «Входящие»,
журнал рассылки, отметка «прочитано»."""

from datetime import timedelta

import pytest
from sqlalchemy import insert, select

from app.models import Email, Job, User
from app.security import hash_password
from tests.helpers import T0, TEST_PASSWORD, auth, create_contest, login, submit_idea, vote

pytestmark = pytest.mark.usefixtures("demo_users")

DAY = timedelta(days=1)
SUB_END = T0 + 2 * DAY
VOTE_END = T0 + 4 * DAY
PARTICIPANTS = ("anna", "boris", "vera", "gleb")
NAMES = ("Анна Смирнова", "Борис Котов", "Вера Орлова", "Глеб Лебедев")


@pytest.fixture
async def t(client, app):
    app.state.settings.session_ttl_hours = 24 * 30  # часы уходят на дни вперёд
    return {u: await login(client, u) for u in ("organizer", "admin", *PARTICIPANTS, "dina")}


@pytest.fixture
async def cid(client, t, user_ids) -> int:
    contest = await create_contest(
        client, t["organizer"], submission_deadline=SUB_END, voting_deadline=VOTE_END,
        participants=[user_ids[u] for u in PARTICIPANTS],
    )
    return contest["id"]


async def letters(app, **filters) -> list[Email]:
    statement = select(Email).order_by(Email.id)
    for column, value in filters.items():
        statement = statement.where(getattr(Email, column) == value)
    async with app.state.sessionmaker() as db:
        return list((await db.scalars(statement)).all())


def logins(rows, user_ids) -> set[str]:
    names = {v: k for k, v in user_ids.items()}
    return {names[row.recipient_id] for row in rows}


async def inbox(client, token, **params):
    return (await client.get("/api/emails", params=params, headers=auth(token))).json()


# --- письма участникам -----------------------------------------------------------------


async def test_participants_are_invited_when_contest_is_created(client, app, t, cid, user_ids, open_tab):
    invitations = await letters(app, kind="invitation")
    assert logins(invitations, user_ids) == set(PARTICIPANTS)  # Дине и организатору — нет
    assert "Как улучшить офис" in invitations[0].subject

    # Сигнал о новом письме — сразу, без перезагрузки.
    anna_tab = await open_tab(t["anna"])
    await create_contest(client, t["organizer"], topic="Второй", participants=[user_ids["anna"]])
    kinds = {(await anna_tab.next())["type"], (await anna_tab.next())["type"]}
    assert kinds == {"contests_changed", "mail_changed"}


async def test_voting_open_goes_to_every_participant(client, app, t, cid, clock, user_ids):
    """Всем участникам, включая автора единственной идеи: иначе по журналу был бы виден автор."""
    await submit_idea(client, t["anna"], cid, "Единственная идея")
    clock.set(SUB_END)
    outcomes = {o.kind: o for o in await app.state.jobs.run_due()}
    assert outcomes["open_voting"].status == "done"

    assert logins(await letters(app, kind="voting_open"), user_ids) == set(PARTICIPANTS)
    [closed] = await letters(app, kind="org_submission_closed")
    assert closed.recipient_id == user_ids["organizer"]
    assert "подано 1 идея" in closed.body


async def test_no_ideas_no_voting_open_and_organizer_is_warned(app, cid, clock, user_ids):
    clock.set(SUB_END)
    await app.state.jobs.run_due()
    assert await letters(app, kind="voting_open") == []
    [closed] = await letters(app, kind="org_submission_closed")
    assert closed.subject.startswith("Идей не подано")
    assert "без победителя" in closed.body


# --- письма организатору ---------------------------------------------------------------


async def test_organizer_gets_summaries_with_numbers_but_no_names_before_final(client, app, t, cid, clock, user_ids):
    first = (await submit_idea(client, t["anna"], cid, "Идея Анны")).json()
    await submit_idea(client, t["boris"], cid, "Идея Бориса")
    clock.set(SUB_END - DAY)
    await app.state.jobs.run_due()
    clock.set(SUB_END)
    await app.state.jobs.run_due()
    await vote(client, t["vera"], first["id"])
    clock.set(VOTE_END - DAY)
    await app.state.jobs.run_due()

    org = await letters(app, recipient_id=user_ids["organizer"])
    assert [e.kind for e in org] == ["org_submission_soon", "org_submission_closed", "org_voting_soon"]
    soon, _, voting_soon = org
    assert "подано 2 идеи" in soon.body and "участникам без идей: 2" in soon.body
    assert "Проголосовали 1 из 4" in voting_soon.body
    # Ни одного имени участника до финала: только числа (D-005, D-058).
    for letter in org:
        assert not any(name in letter.subject + letter.body for name in NAMES)

    clock.set(VOTE_END)
    await app.state.jobs.run_due()
    [final] = await letters(app, recipient_id=user_ids["organizer"], kind="final")
    assert final.subject == "Конкурс завершён: «Как улучшить офис»"
    assert "Победила идея «Идея Анны» (автор: Анна Смирнова, 1 голос)" in final.body


async def test_only_the_creator_gets_organizer_letters(client, app, t, cid, clock, user_ids):
    async with app.state.sessionmaker() as db:
        await db.execute(insert(User).values(
            login="org2", display_name="Второй организатор", email="org2@example.com", role="organizer",
            password_hash=hash_password(TEST_PASSWORD), created_at=T0,
        ))
        await db.commit()
    other = await login(client, "org2")
    clock.set(VOTE_END)
    await app.state.jobs.run_due()
    assert await inbox(client, other) == []
    # Сервер «проспал» сроки: напоминания и «голосование открыто» пропущены, итоги — пришли.
    assert [e["kind"] for e in await inbox(client, t["organizer"])] == ["final"]


async def test_failed_job_notifies_the_organizer(app, cid, clock, monkeypatch, user_ids):
    from app.jobs import JobRunner

    async def broken(*args, **kwargs):
        raise RuntimeError("почтовый сервер недоступен")

    monkeypatch.setattr(JobRunner, "execute", staticmethod(broken))
    clock.set(SUB_END - DAY)
    for _ in range(5):  # пять попыток с паузами между ними
        await app.state.jobs.run_due()
        clock.advance(timedelta(minutes=1))
    async with app.state.sessionmaker() as db:
        job = await db.scalar(select(Job).where(Job.contest_id == cid, Job.kind == "remind_submission"))
    assert job.status == "failed"
    [letter] = await letters(app, kind="org_job_failed")
    assert letter.recipient_id == user_ids["organizer"]
    assert "напоминание о подаче идей" in letter.body


# --- «Входящие» и журнал -----------------------------------------------------------------


async def test_unread_letters_and_marking_them_read(client, app, t, cid, user_ids):
    assert (await client.get("/api/emails/unread-count", headers=auth(t["anna"]))).json() == {"count": 1}
    [letter] = await inbox(client, t["anna"])
    assert letter["read_at"] is None

    # Чужое письмо отметить нельзя — «не найдено», как и несуществующее.
    assert (await client.post(f"/api/emails/{letter['id']}/read", headers=auth(t["boris"]))).status_code == 404
    assert (await client.post(f"/api/emails/{letter['id']}/read", headers=auth(t["anna"]))).status_code == 204
    assert (await inbox(client, t["anna"]))[0]["read_at"] is not None
    assert await inbox(client, t["anna"], unread="true") == []
    assert (await client.get("/api/emails/unread-count", headers=auth(t["boris"]))).json() == {"count": 1}

    await client.post("/api/emails/read-all", headers=auth(t["boris"]))
    assert (await client.get("/api/emails/unread-count", headers=auth(t["boris"]))).json() == {"count": 0}
    assert (await client.get("/api/emails/unread-count", headers=auth(t["vera"]))).json() == {"count": 1}


async def test_journal_is_for_organizer_and_admin_with_search(client, t, cid):
    for who in ("organizer", "admin"):
        journal = (await client.get("/api/emails/journal", headers=auth(t[who]))).json()
        assert {e["kind"] for e in journal} == {"invitation"}
        assert all(e["read_at"] is None for e in journal)  # журнал не раскрывает, кто что прочитал
    found = await client.get("/api/emails/journal", params={"recipient": "котов"}, headers=auth(t["admin"]))
    assert [e["recipient"]["display_name"] for e in found.json()] == ["Борис Котов"]
    by_mail = await client.get("/api/emails/journal", params={"recipient": "vera@"}, headers=auth(t["admin"]))
    assert [e["to_address"] for e in by_mail.json()] == ["vera@example.com"]
    wildcard = await client.get("/api/emails/journal", params={"recipient": "%"}, headers=auth(t["admin"]))
    assert wildcard.json() == []  # «%» ищется буквально, а не как «что угодно»
    final_only = await client.get("/api/emails/journal", params={"kind": "final"}, headers=auth(t["admin"]))
    assert final_only.json() == []
    assert (await client.get("/api/emails/journal", headers=auth(t["anna"]))).status_code == 403



async def test_journal_never_points_at_authors_before_final(client, app, t, cid, clock, user_ids):
    """Анонимность журнала (D-058, приёмка версии 2): до финала у каждого вида письма в журнале
    получатели — либо все участники, либо только организатор. Иначе по тому, кому письмо
    пришло или не пришло, можно вычислить, кто подавал идеи и кто голосовал."""
    await submit_idea(client, t["anna"], cid, "Идея Анны")  # все идеи — от одного автора
    await submit_idea(client, t["anna"], cid, "Ещё идея Анны")
    for moment in (SUB_END - DAY, SUB_END, VOTE_END - DAY):
        clock.set(moment)
        await app.state.jobs.run_due()
        for who in ("organizer", "admin"):
            journal = (await client.get("/api/emails/journal", params={"contest_id": cid}, headers=auth(t[who]))).json()
            by_kind: dict[str, set[int]] = {}
            for letter in journal:
                by_kind.setdefault(letter["kind"], set()).add(letter["recipient"]["id"])
            everyone = {user_ids[u] for u in PARTICIPANTS}
            for kind, recipients in by_kind.items():
                assert recipients in (everyone, {user_ids["organizer"]}), (moment, kind, recipients)
