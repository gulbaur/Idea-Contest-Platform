"""Демо-конкурсы (D-054): фазы, видимость, ничья, письма — по тем же правилам, что и в работе."""

import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.demo import DEMO_CONTESTS, create_demo_contests
from app.models import Contest, Email, Job, User
from app.seed import seed_demo_data
from tests.helpers import T0, auth, login, snapshot

pytestmark = pytest.mark.usefixtures("demo_users")

LEAD = timedelta(hours=24)
NAMES = ["Анна Смирнова", "Борис Котов", "Вера Орлова", "Глеб Лебедев", "Дина Ахметова"]


@pytest.fixture
async def demo(app, clock) -> dict[str, int]:
    """Фаза → номер демо-конкурса."""
    async with app.state.sessionmaker() as db:
        ids = await create_demo_contests(db, clock, LEAD)
    return dict(zip(("finished", "voting", "submission"), ids, strict=True))


async def letters(app, contest_id: int) -> dict[str, set[str]]:
    """Вид письма → логины получателей."""
    async with app.state.sessionmaker() as db:
        rows = await db.execute(
            select(Email.kind, User.login).join(User, User.id == Email.recipient_id).where(Email.contest_id == contest_id)
        )
    result: dict[str, set[str]] = {}
    for kind, user_login in rows:
        result.setdefault(kind, set()).add(user_login)
    return result


async def job_statuses(app, contest_id: int) -> dict[str, str]:
    async with app.state.sessionmaker() as db:
        return dict((await db.execute(select(Job.kind, Job.status).where(Job.contest_id == contest_id))).all())


async def test_demo_contests_are_in_all_three_phases(client, demo):
    org = await login(client, "organizer")
    listed = {c["id"]: c["phase"] for c in (await client.get("/api/contests", headers=auth(org))).json()}
    assert listed == {cid: phase for phase, cid in demo.items()}


async def test_demo_history_happened_in_the_right_phases(app, demo):
    """Каждая идея подана во время приёма, каждый голос — во время голосования."""
    async with app.state.sessionmaker() as db:
        contests = {c.id: c for c in (await db.scalars(select(Contest))).all()}
    for spec, contest_id in zip(DEMO_CONTESTS, demo.values(), strict=True):
        contest = contests[contest_id]
        assert contest.created_at < contest.submission_deadline < contest.voting_deadline
        for idea in spec.ideas:
            assert contest.created_at <= contest.created_at - spec.created + idea.submitted < contest.submission_deadline
        authors = {idea.key: idea.author for idea in spec.ideas}
        for vote in spec.votes:
            moment = contest.created_at - spec.created + vote.cast
            assert contest.submission_deadline <= moment < min(contest.voting_deadline, T0)
            assert authors[vote.idea] != vote.voter, "голос за свою идею"
            assert vote.voter in spec.participants
        assert {idea.author for idea in spec.ideas} <= set(spec.participants)


async def test_finished_demo_tie_is_won_by_the_earlier_idea(client, demo, app):
    anna = await login(client, "anna")
    snap = (await snapshot(client, anna, demo["finished"])).json()

    ranking = [(i["title"], i["votes_count"], i["author"]["display_name"]) for i in snap["ideas"]]
    assert ranking == [
        ("Предзаказ обедов через чат-бот", 2, "Борис Котов"),
        ("Микроволновки на каждом этаже", 2, "Вера Орлова"),
        ("Общий стол на летней террасе", 1, "Анна Смирнова"),
        ("Фруктовый день по пятницам", 0, "Анна Смирнова"),
    ]
    winner, runner_up = snap["ideas"][:2]
    assert snap["winner_idea_id"] == winner["id"]
    assert winner["submitted_at"][:16] == runner_up["submitted_at"][:16]  # та же минута
    assert winner["submitted_at"] < runner_up["submitted_at"]  # но на 27 секунд раньше
    assert [i["title"] for i in snap["ideas"] if i["voted_by_me"]] == [
        "Предзаказ обедов через чат-бот",
        "Микроволновки на каждом этаже",
    ]


async def test_finished_demo_letters_follow_the_real_rules(client, demo, app):
    assert await letters(app, demo["finished"]) == {
        # Анна подала идеи уже после напоминания, Глеб не подал совсем.
        "reminder_submission": {"anna", "gleb"},
        # Глеб проголосовал только после напоминания.
        "reminder_voting": {"gleb"},
        "final": {"anna", "boris", "vera", "gleb"},
    }
    assert set((await job_statuses(app, demo["finished"])).values()) == {"done"}
    boris = await login(client, "boris")
    mail = (await client.get("/api/emails", headers=auth(boris))).json()
    final = next(m for m in mail if m["kind"] == "final")
    assert final["subject"] == "Ваша идея победила в конкурсе «Как сделать обеды в офисе удобнее»"
    assert "1. Предзаказ обедов через чат-бот — 2 голоса — автор: Борис Котов" in final["body"]


async def test_voting_demo_hides_authors_and_waits_for_votes(client, demo, app):
    anna = await login(client, "anna")
    response = await snapshot(client, anna, demo["voting"])
    snap = response.json()

    assert len(snap["ideas"]) == 4
    assert not any(name in response.text for name in NAMES)  # ни одного автора в ответе
    assert [i["title"] for i in snap["ideas"] if i["is_mine"]] == ["Совещания стоя — не дольше 15 минут"]
    assert not any(i["voted_by_me"] for i in snap["ideas"])  # Анна ещё не голосовала

    org = await login(client, "organizer")
    org_response = await snapshot(client, org, demo["voting"])
    assert org_response.json()["stats"] == {
        "participants_count": 5,
        "ideas_count": 4,
        "voters_count": 4,
        "votes_count": 4,
    }
    assert not any(name in org_response.text for name in NAMES)
    assert await letters(app, demo["voting"]) == {"reminder_submission": {"gleb", "dina"}}
    assert await job_statuses(app, demo["voting"]) == {
        "remind_submission": "done",
        "remind_voting": "pending",
        "finalize": "pending",
    }


async def test_submission_demo_shows_each_participant_only_own_ideas(client, demo, app):
    async def own_titles(user_login):
        token = await login(client, user_login)
        return sorted(i["title"] for i in (await snapshot(client, token, demo["submission"])).json()["ideas"])

    assert await own_titles("anna") == ["Живые растения в опенспейсе", "Тихая комната для звонков"]
    assert await own_titles("boris") == ["Пледы и мягкие кресла в зоне отдыха"]
    assert await own_titles("vera") == []

    org = await login(client, "organizer")
    org_snap = (await snapshot(client, org, demo["submission"])).json()
    assert (org_snap["ideas"], org_snap["stats"]["ideas_count"]) == ([], 3)
    assert await letters(app, demo["submission"]) == {}

    dina = await login(client, "dina")  # не участвует
    assert (await snapshot(client, dina, demo["submission"])).status_code == 404


async def test_nothing_overdue_is_left_for_the_job_runner(app, demo):
    """Прошлые задания уже «проиграны»: обработчику нечего делать задним числом."""
    assert await app.state.jobs.run_due() == []


async def test_demo_set_can_be_added_again(app, clock, demo):
    async with app.state.sessionmaker() as db:
        await create_demo_contests(db, clock, LEAD)
        assert await db.scalar(select(func.count()).select_from(Contest)) == 6


@pytest.mark.parametrize("lead", [timedelta(seconds=10), timedelta(days=30)], ids=["short", "longer-than-rounds"])
async def test_demo_works_with_any_reminder_lead(app, clock, lead, client):
    async with app.state.sessionmaker() as db:
        ids = await create_demo_contests(db, clock, lead)
    org = await login(client, "organizer")
    phases = [c["phase"] for c in (await client.get("/api/contests", headers=auth(org))).json()]
    assert sorted(phases) == ["finished", "submission", "voting"]
    assert {"final"} <= set(await letters(app, ids[0]))


async def test_seed_adds_demo_contests_only_to_an_empty_database(app, clock, settings):
    async with app.state.sessionmaker() as db:
        first = await seed_demo_data(db, settings, clock)
        second = await seed_demo_data(db, settings, clock)
        count = await db.scalar(select(func.count()).select_from(Contest))
    assert first[1].startswith("созданы демо-конкурсы")
    assert second[1].startswith("конкурсы уже есть")
    assert count == len(DEMO_CONTESTS)


async def test_demo_texts_contain_no_personal_data():
    """Только синтетические данные: без адресов, телефонов и ссылок."""
    text = json.dumps([spec.__repr__() for spec in DEMO_CONTESTS], ensure_ascii=False)
    for marker in ("@", "http", "+7", "www."):
        assert marker not in text
