"""Кто что видит в каждой фазе (F11, F12, F6, F16; D-005, D-028).

Проверяется не только структура ответа, но и весь текст JSON: чужие названия
идей и имена авторов не должны встречаться там, где их не должно быть.
"""

import pytest

from tests.helpers import (
    SUBMISSION_END,
    T0,
    VOTING_END,
    auth,
    create_contest,
    login,
    snapshot,
    submit_idea,
)

pytestmark = pytest.mark.usefixtures("demo_users")

ANNA_IDEA = "Идея-Анны-7f3a"
BORIS_IDEA = "Идея-Бориса-91c2"
AUTHOR_NAMES = ("Анна Смирнова", "Борис Котов")


@pytest.fixture
async def world(client, user_ids):
    """Конкурс: участники anna, boris, vera; anna и boris подали по идее; dina — не участник."""
    tokens = {u: await login(client, u) for u in ("organizer", "anna", "boris", "vera", "dina")}
    contest = await create_contest(
        client,
        tokens["organizer"],
        participants=[user_ids[u] for u in ("anna", "boris", "vera")],
    )
    assert (await submit_idea(client, tokens["anna"], contest["id"], ANNA_IDEA)).status_code == 201
    assert (await submit_idea(client, tokens["boris"], contest["id"], BORIS_IDEA)).status_code == 201
    return {"contest_id": contest["id"], "tokens": tokens}


async def view(client, world, who: str):
    response = await snapshot(client, world["tokens"][who], world["contest_id"])
    assert response.status_code == 200, response.text
    return response.json(), response.text


# --- подача -----------------------------------------------------------------


async def test_submission_participant_sees_only_own_ideas(client, world):
    body, raw = await view(client, world, "anna")

    assert body["contest"]["phase"] == "submission"
    assert [i["title"] for i in body["ideas"]] == [ANNA_IDEA]
    assert BORIS_IDEA not in raw
    assert body["stats"] is None


async def test_submission_participant_without_ideas_sees_nothing(client, world):
    body, raw = await view(client, world, "vera")

    assert body["ideas"] == []
    assert ANNA_IDEA not in raw and BORIS_IDEA not in raw


async def test_submission_organizer_sees_only_counters(client, world):
    body, raw = await view(client, world, "organizer")

    assert body["ideas"] == []
    assert body["stats"] == {"participants_count": 3, "ideas_count": 2}
    assert ANNA_IDEA not in raw and BORIS_IDEA not in raw


# --- голосование ------------------------------------------------------------


@pytest.mark.parametrize("who", ["anna", "vera", "organizer"])
async def test_voting_everyone_sees_all_ideas_without_authors(client, world, clock, who):
    clock.set(SUBMISSION_END)

    body, raw = await view(client, world, who)

    assert body["contest"]["phase"] == "voting"
    assert sorted(i["title"] for i in body["ideas"]) == sorted([ANNA_IDEA, BORIS_IDEA])
    assert all(i["author"] is None for i in body["ideas"])
    for name in AUTHOR_NAMES:
        assert name not in raw


async def test_voting_participant_sees_which_ideas_are_own(client, world, clock):
    clock.set(SUBMISSION_END)

    body, _ = await view(client, world, "anna")

    mine = {i["title"]: i["is_mine"] for i in body["ideas"]}
    assert mine == {ANNA_IDEA: True, BORIS_IDEA: False}


async def test_voting_stats_only_for_organizer(client, world, clock):
    clock.set(SUBMISSION_END)
    assert (await view(client, world, "anna"))[0]["stats"] is None
    assert (await view(client, world, "organizer"))[0]["stats"]["ideas_count"] == 2


# --- финал ------------------------------------------------------------------


@pytest.mark.parametrize("who", ["anna", "vera", "organizer"])
async def test_finished_everyone_sees_authors(client, world, clock, who):
    clock.set(VOTING_END)

    body, _ = await view(client, world, who)

    assert body["contest"]["phase"] == "finished"
    authors = {i["title"]: i["author"]["display_name"] for i in body["ideas"]}
    assert authors == {ANNA_IDEA: "Анна Смирнова", BORIS_IDEA: "Борис Котов"}


# --- не участник ------------------------------------------------------------


@pytest.mark.parametrize("moment", ["submission", "voting", "finished"])
async def test_non_participant_sees_nothing_in_any_phase(client, world, clock, moment):
    clock.set({"submission": T0, "voting": SUBMISSION_END, "finished": VOTING_END}[moment])
    response = await snapshot(client, world["tokens"]["dina"], world["contest_id"])
    assert response.status_code == 404
    contests = await client.get("/api/contests", headers=auth(world["tokens"]["dina"]))
    assert contests.json() == []


async def test_snapshot_reports_server_time_and_revision(client, world, clock):
    body, _ = await view(client, world, "anna")
    assert body["revision"] == 3  # создание + две подачи
    assert body["server_time"].startswith(clock.now().strftime("%Y-%m-%dT%H:%M:%S"))
