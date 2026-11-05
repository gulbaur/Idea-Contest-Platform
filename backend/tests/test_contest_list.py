"""Строки списка конкурсов (D-061): счётчики организатору, своё участие сотруднику, без утечек."""

from datetime import timedelta

import pytest

from tests.helpers import SUBMISSION_END, VOTING_END, auth, create_contest, login, submit_idea, vote

pytestmark = pytest.mark.usefixtures("demo_users")


async def _listed(client, token: str, contest_id: int) -> dict:
    items = (await client.get("/api/contests", headers=auth(token))).json()
    return next(item for item in items if item["id"] == contest_id)


@pytest.fixture
async def world(client, user_ids):
    org = await login(client, "organizer")
    tokens = {name: await login(client, name) for name in ("anna", "boris", "vera")}
    contest = await create_contest(
        client, org, participants=[user_ids["anna"], user_ids["boris"], user_ids["vera"]]
    )
    first = (await submit_idea(client, tokens["anna"], contest["id"], "Идея Анны")).json()
    await submit_idea(client, tokens["anna"], contest["id"], "Вторая идея Анны")
    return {"org": org, "tokens": tokens, "contest": contest, "anna_idea": first}


async def test_participant_sees_only_own_participation_during_submission(client, world):
    anna = await _listed(client, world["tokens"]["anna"], world["contest"]["id"])
    boris = await _listed(client, world["tokens"]["boris"], world["contest"]["id"])

    assert anna["my"] == {"ideas_count": 2, "votes_count": 0, "can_vote": False}
    # Борис не узнаёт, что Анна уже подала идеи: ни счётчиков, ни «есть за кого голосовать».
    assert boris["my"] == {"ideas_count": 0, "votes_count": 0, "can_vote": False}
    assert boris["stats"] is None


async def test_organizer_sees_counts_but_not_voters_before_voting(client, world):
    org = await _listed(client, world["org"], world["contest"]["id"])
    assert org["stats"] == {"participants_count": 3, "ideas_count": 2, "voters_count": None}
    assert org["my"] is None


async def test_voting_phase_counts_and_can_vote(client, clock, world):
    clock.set(SUBMISSION_END + timedelta(minutes=1))
    tokens = world["tokens"]
    await vote(client, tokens["boris"], world["anna_idea"]["id"])

    boris = await _listed(client, tokens["boris"], world["contest"]["id"])
    vera = await _listed(client, tokens["vera"], world["contest"]["id"])
    anna = await _listed(client, tokens["anna"], world["contest"]["id"])
    org = await _listed(client, world["org"], world["contest"]["id"])

    assert boris["my"] == {"ideas_count": 0, "votes_count": 1, "can_vote": True}
    assert vera["my"] == {"ideas_count": 0, "votes_count": 0, "can_vote": True}  # «нужно проголосовать»
    # У Анны только свои идеи — голосовать не за что.
    assert anna["my"] == {"ideas_count": 2, "votes_count": 0, "can_vote": False}
    assert org["stats"] == {"participants_count": 3, "ideas_count": 2, "voters_count": 1}


async def test_finished_contest_cannot_be_voted_in_list(client, clock, world):
    clock.set(VOTING_END)
    vera = await _listed(client, world["tokens"]["vera"], world["contest"]["id"])
    assert vera["my"]["can_vote"] is False
    assert vera["phase"] == "finished"


async def test_list_uses_a_fixed_number_of_queries(client, user_ids, app):
    """Счётчики — групповыми запросами на весь список, а не запросом на каждый конкурс."""
    from sqlalchemy import event

    org = await login(client, "organizer")
    for n in range(12):
        await create_contest(client, org, topic=f"Конкурс {n}", participants=[user_ids["anna"]])
    anna = await login(client, "anna")

    statements: list[str] = []

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    engine = app.state.engine.sync_engine
    event.listen(engine, "before_cursor_execute", count)
    try:
        for token in (org, anna):
            statements.clear()
            assert len((await client.get("/api/contests", headers=auth(token))).json()) == 12
            assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) <= 6
    finally:
        event.remove(engine, "before_cursor_execute", count)
