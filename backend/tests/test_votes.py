"""Голосование: права, сроки, повторы, параллельные запросы (F5, F13, F14, F19; D-033, D-034)."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Vote
from tests.helpers import (
    SUBMISSION_END,
    VOTING_END,
    auth,
    create_contest,
    login,
    revoke,
    snapshot,
    submit_idea,
    vote,
)

pytestmark = pytest.mark.usefixtures("demo_users")

TICK = timedelta(microseconds=1)


@pytest.fixture
async def world(client, user_ids, clock):
    """Участники anna, boris, vera; anna подала 2 идеи, boris — 1; часы — в фазе голосования."""
    t = {u: await login(client, u) for u in ("organizer", "anna", "boris", "vera", "dina")}
    contest = await create_contest(
        client, t["organizer"], participants=[user_ids[u] for u in ("anna", "boris", "vera")]
    )
    cid = contest["id"]
    a1 = (await submit_idea(client, t["anna"], cid, "Анна-1")).json()["id"]
    a2 = (await submit_idea(client, t["anna"], cid, "Анна-2")).json()["id"]
    b1 = (await submit_idea(client, t["boris"], cid, "Борис-1")).json()["id"]
    clock.set(SUBMISSION_END)
    return {"t": t, "cid": cid, "a1": a1, "a2": a2, "b1": b1}


async def votes_in_db(app, **filters) -> int:
    statement = select(func.count()).select_from(Vote)
    for column, value in filters.items():
        statement = statement.where(getattr(Vote, column) == value)
    async with app.state.sessionmaker() as db:
        return await db.scalar(statement)


async def org_stats(client, world) -> dict:
    return (await snapshot(client, world["t"]["organizer"], world["cid"])).json()["stats"]


# --- права ------------------------------------------------------------------


async def test_participant_votes_for_other_idea(client, world, app):
    response = await vote(client, world["t"]["boris"], world["a1"])

    assert response.status_code == 201
    assert response.json() == {"idea_id": world["a1"], "voted": True}
    assert await votes_in_db(app, idea_id=world["a1"]) == 1


async def test_cannot_vote_for_own_idea(client, world, app):
    response = await vote(client, world["t"]["anna"], world["a1"])

    assert response.status_code == 403
    assert response.json()["detail"] == "Нельзя голосовать за свою идею"
    assert await votes_in_db(app) == 0


async def test_participant_can_vote_for_several_different_ideas(client, world, app):
    """«Один голос на идею», а не «один голос на конкурс»."""
    boris = world["t"]["boris"]
    assert (await vote(client, boris, world["a1"])).status_code == 201
    assert (await vote(client, boris, world["a2"])).status_code == 201
    assert await votes_in_db(app, voter_id=(await _me(client, boris))["id"]) == 2


async def test_participant_without_ideas_can_vote(client, world):
    assert (await vote(client, world["t"]["vera"], world["b1"])).status_code == 201


async def test_organizer_cannot_vote(client, world):
    response = await vote(client, world["t"]["organizer"], world["a1"])
    assert response.status_code == 403
    assert response.json()["detail"] == "Организатор не голосует"


async def test_non_participant_cannot_vote(client, world):
    assert (await vote(client, world["t"]["dina"], world["a1"])).status_code == 404


async def test_unknown_idea_is_404(client, world):
    assert (await vote(client, world["t"]["boris"], 999999)).status_code == 404
    assert (await revoke(client, world["t"]["boris"], 999999)).status_code == 404


# --- сроки ------------------------------------------------------------------


async def test_voting_not_open_during_submission(client, world, clock):
    clock.set(SUBMISSION_END - TICK)
    response = await vote(client, world["t"]["boris"], world["a1"])
    assert response.status_code == 409
    assert response.json()["detail"] == "Голосование ещё не началось"


async def test_vote_accepted_until_last_moment_and_rejected_exactly_at_deadline(
    client, world, clock, app
):
    boris = world["t"]["boris"]
    clock.set(VOTING_END - TICK)
    assert (await vote(client, boris, world["a1"])).status_code == 201

    clock.set(VOTING_END)
    response = await vote(client, boris, world["a2"])
    assert response.status_code == 409
    assert response.json()["detail"] == "Голосование закрыто"
    assert await votes_in_db(app) == 1


async def test_revoke_before_deadline_and_rejected_after(client, world, clock, app):
    boris = world["t"]["boris"]
    await vote(client, boris, world["a1"])
    await vote(client, boris, world["a2"])

    clock.set(VOTING_END - TICK)
    assert (await revoke(client, boris, world["a1"])).status_code == 204
    assert await votes_in_db(app, idea_id=world["a1"]) == 0

    clock.set(VOTING_END)  # старая страница пытается отозвать голос после закрытия
    assert (await revoke(client, boris, world["a2"])).status_code == 409
    assert await votes_in_db(app, idea_id=world["a2"]) == 1


# --- повторы ----------------------------------------------------------------


async def test_repeated_vote_keeps_one_vote(client, world, app):
    boris = world["t"]["boris"]
    first = await vote(client, boris, world["a1"])
    second = await vote(client, boris, world["a1"])

    assert (first.status_code, second.status_code) == (201, 200)
    assert await votes_in_db(app) == 1


async def test_repeated_revoke_and_vote_again(client, world, app):
    boris = world["t"]["boris"]
    await vote(client, boris, world["a1"])

    assert (await revoke(client, boris, world["a1"])).status_code == 204
    assert (await revoke(client, boris, world["a1"])).status_code == 204  # повтор — без ошибки
    assert await votes_in_db(app) == 0

    assert (await vote(client, boris, world["a1"])).status_code == 201  # голос можно вернуть
    assert await votes_in_db(app) == 1


async def test_two_tabs_of_same_user_still_one_vote(client, world, app):
    tab_a, tab_b = await login(client, "boris"), await login(client, "boris")

    assert (await vote(client, tab_a, world["a1"])).status_code == 201
    assert (await vote(client, tab_b, world["a1"])).status_code == 200
    assert await votes_in_db(app) == 1
    snap = (await snapshot(client, tab_b, world["cid"])).json()
    assert {i["id"]: i["voted_by_me"] for i in snap["ideas"]}[world["a1"]] is True


async def test_revision_changes_only_when_vote_state_changes(client, world):
    boris = world["t"]["boris"]

    async def revision() -> int:
        return (await snapshot(client, world["t"]["organizer"], world["cid"])).json()["revision"]

    start = await revision()
    await vote(client, boris, world["a1"])
    assert await revision() == start + 1
    await vote(client, boris, world["a1"])  # повтор
    assert await revision() == start + 1
    await revoke(client, boris, world["a1"])
    assert await revision() == start + 2
    await revoke(client, boris, world["a1"])  # повтор
    assert await revision() == start + 2
    await vote(client, world["t"]["anna"], world["a1"])  # отклонено: своя идея
    assert await revision() == start + 2


# --- параллельные запросы (независимые соединения БД) -------------------------


async def test_parallel_identical_votes_create_one_vote(client, world, app):
    boris = world["t"]["boris"]

    responses = await asyncio.gather(*(vote(client, boris, world["a1"]) for _ in range(10)))

    assert sorted(r.status_code for r in responses) == [200] * 9 + [201]
    assert await votes_in_db(app) == 1


async def test_parallel_votes_from_different_users_are_all_counted(client, world):
    tabs = [world["t"]["boris"], world["t"]["vera"], await login(client, "vera")]

    responses = await asyncio.gather(*(vote(client, t, world["a1"]) for t in tabs))

    assert sorted(r.status_code for r in responses) == [200, 201, 201]
    stats = await org_stats(client, world)
    assert stats["votes_count"] == 2
    assert stats["voters_count"] == 2


async def test_database_itself_rejects_duplicate_vote(app, world, user_ids):
    """Уникальность обеспечивает ограничение БД, а не только код (P3)."""
    row = {
        "idea_id": world["a1"],
        "voter_id": user_ids["boris"],
        "contest_id": world["cid"],
        "created_at": datetime.now(UTC),
    }
    async with app.state.sessionmaker() as db:
        db.add(Vote(**row))
        await db.commit()
    async with app.state.sessionmaker() as db:
        db.add(Vote(**row))
        with pytest.raises(IntegrityError):
            await db.commit()


# --- удаление идеи вместе с голосами ------------------------------------------


async def test_deleting_idea_removes_its_votes_atomically(client, world, app):
    t = world["t"]
    await vote(client, t["boris"], world["a1"])
    await vote(client, t["vera"], world["a1"])
    await vote(client, t["vera"], world["b1"])
    assert (await org_stats(client, world))["voters_count"] == 2

    response = await client.delete(f"/api/ideas/{world['a1']}", headers=auth(t["anna"]))

    assert response.status_code == 204
    assert await votes_in_db(app, idea_id=world["a1"]) == 0
    assert await votes_in_db(app, idea_id=world["b1"]) == 1  # чужие голоса не затронуты
    stats = await org_stats(client, world)
    assert stats == {"participants_count": 3, "ideas_count": 2, "voters_count": 1, "votes_count": 1}
    titles = [i["title"] for i in (await snapshot(client, t["vera"], world["cid"])).json()["ideas"]]
    assert "Анна-1" not in titles


async def test_vote_for_deleted_idea_is_404(client, world):
    await client.delete(f"/api/ideas/{world['a1']}", headers=auth(world["t"]["anna"]))
    response = await vote(client, world["t"]["boris"], world["a1"])
    assert response.status_code == 404


@pytest.mark.parametrize("attempt", range(5))
async def test_parallel_vote_and_delete_leave_no_orphan_votes(client, world, app, attempt):
    """Голос и удаление той же идеи одновременно: при любом порядке голосов за неё не остаётся."""
    t = world["t"]

    vote_response, delete_response = await asyncio.gather(
        vote(client, t["boris"], world["a2"]),
        client.delete(f"/api/ideas/{world['a2']}", headers=auth(t["anna"])),
    )

    assert delete_response.status_code == 204
    # Голос либо успел до удаления (201, затем удалён каскадом), либо пришёл после (404).
    assert vote_response.status_code in (201, 404)
    assert await votes_in_db(app, idea_id=world["a2"]) == 0
    assert (await org_stats(client, world))["voters_count"] == 0


async def _me(client, token) -> dict:
    return (await client.get("/api/auth/me", headers=auth(token))).json()
