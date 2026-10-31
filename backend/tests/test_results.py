"""Результаты, победитель, ничья, проголосовавшие, анонимность (F6, F8, F15, F16, F18; D-035 … D-037)."""

from datetime import timedelta

import pytest

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

PARTICIPANTS = ("anna", "boris", "vera", "gleb")


@pytest.fixture
async def tokens(client) -> dict[str, str]:
    return {u: await login(client, u) for u in ("organizer", *PARTICIPANTS)}


@pytest.fixture
async def contest_id(client, tokens, user_ids) -> int:
    contest = await create_contest(
        client, tokens["organizer"], participants=[user_ids[u] for u in PARTICIPANTS]
    )
    return contest["id"]


async def submit(client, tokens, contest_id, who, title) -> int:
    response = await submit_idea(client, tokens[who], contest_id, title)
    assert response.status_code == 201
    return response.json()["id"]


async def view(client, tokens, contest_id, who) -> dict:
    response = await snapshot(client, tokens[who], contest_id)
    assert response.status_code == 200
    return response.json()


def titles(snap) -> list[str]:
    return [i["title"] for i in snap["ideas"]]


# --- видимость результатов --------------------------------------------------


async def test_results_hidden_from_participants_during_voting(client, tokens, contest_id, clock):
    a = await submit(client, tokens, contest_id, "anna", "A")
    await submit(client, tokens, contest_id, "boris", "B")
    clock.set(SUBMISSION_END)
    await vote(client, tokens["boris"], a)
    await vote(client, tokens["vera"], a)

    for who in ("anna", "boris", "vera", "gleb"):
        snap = await view(client, tokens, contest_id, who)
        assert all(i["votes_count"] is None for i in snap["ideas"]), who
        assert snap["stats"] is None and snap["winner_idea_id"] is None
        assert titles(snap) == ["A", "B"]  # порядок подачи — не выдаёт лидера


async def test_organizer_sees_live_results_during_voting(client, tokens, contest_id, clock):
    a = await submit(client, tokens, contest_id, "anna", "A")
    b = await submit(client, tokens, contest_id, "boris", "B")
    clock.set(SUBMISSION_END)

    await vote(client, tokens["anna"], b)
    snap = await view(client, tokens, contest_id, "organizer")
    assert [(i["title"], i["votes_count"]) for i in snap["ideas"]] == [("B", 1), ("A", 0)]
    assert snap["winner_idea_id"] is None  # победитель — только после финала

    await vote(client, tokens["boris"], a)
    await vote(client, tokens["vera"], a)
    snap = await view(client, tokens, contest_id, "organizer")
    assert [(i["title"], i["votes_count"]) for i in snap["ideas"]] == [("A", 2), ("B", 1)]
    assert all(i["author"] is None for i in snap["ideas"])  # авторов организатор не видит


async def test_everyone_sees_results_and_winner_after_final(client, tokens, contest_id, clock):
    a = await submit(client, tokens, contest_id, "anna", "A")
    b = await submit(client, tokens, contest_id, "boris", "B")
    clock.set(SUBMISSION_END)
    await vote(client, tokens["anna"], b)
    await vote(client, tokens["vera"], b)
    await vote(client, tokens["gleb"], a)
    clock.set(VOTING_END)

    for who in ("organizer", "anna", "gleb"):
        snap = await view(client, tokens, contest_id, who)
        assert snap["winner_idea_id"] == b, who
        assert [(i["title"], i["votes_count"], i["author"]["display_name"]) for i in snap["ideas"]] == [
            ("B", 2, "Борис Котов"),
            ("A", 1, "Анна Смирнова"),
        ]


async def test_votes_stay_anonymous(client, tokens, contest_id, clock):
    """Никто не видит, кто за что голосовал; участник видит только свои голоса."""
    a = await submit(client, tokens, contest_id, "anna", "A")
    clock.set(SUBMISSION_END)
    await vote(client, tokens["boris"], a)

    vera = await view(client, tokens, contest_id, "vera")
    boris = await view(client, tokens, contest_id, "boris")
    assert vera["ideas"][0]["voted_by_me"] is False
    assert boris["ideas"][0]["voted_by_me"] is True

    clock.set(VOTING_END)
    for who in ("organizer", "anna", "vera"):
        response = await snapshot(client, tokens[who], contest_id)
        assert "Борис Котов" not in response.text, who  # имя голосовавшего нигде не появляется
        assert "voter_id" not in response.text  # в ответе нет связи «голосующий — идея»


# --- победитель и ничья -----------------------------------------------------


async def test_tie_is_won_by_earlier_idea_even_after_edit(client, tokens, contest_id, clock):
    early = await submit(client, tokens, contest_id, "anna", "Ранняя")
    clock.advance(timedelta(minutes=5))
    late = await submit(client, tokens, contest_id, "boris", "Поздняя")
    clock.advance(timedelta(minutes=5))
    # Правка ранней идеи не меняет время подачи (D-008).
    response = await client.put(
        f"/api/ideas/{early}",
        json={"title": "Ранняя (исправлена)", "description": "Текст", "version": 1},
        headers=auth(tokens["anna"]),
    )
    assert response.status_code == 200

    clock.set(SUBMISSION_END)
    await vote(client, tokens["vera"], early)
    await vote(client, tokens["gleb"], late)
    clock.set(VOTING_END)

    snap = await view(client, tokens, contest_id, "gleb")
    assert snap["winner_idea_id"] == early
    assert titles(snap) == ["Ранняя (исправлена)", "Поздняя"]


async def test_tie_with_identical_submit_time_is_won_by_lower_id(client, tokens, contest_id, clock):
    # Управляемые часы стоят на месте: обе идеи получают одинаковое submitted_at.
    first = await submit(client, tokens, contest_id, "boris", "Первая")
    second = await submit(client, tokens, contest_id, "anna", "Вторая")
    clock.set(SUBMISSION_END)
    await vote(client, tokens["vera"], first)
    await vote(client, tokens["vera"], second)
    clock.set(VOTING_END)

    snap = await view(client, tokens, contest_id, "anna")
    assert snap["ideas"][0]["submitted_at"] == snap["ideas"][1]["submitted_at"]
    assert first < second
    assert snap["winner_idea_id"] == first


async def test_more_votes_beat_earlier_submission(client, tokens, contest_id, clock):
    early = await submit(client, tokens, contest_id, "anna", "Ранняя")
    clock.advance(timedelta(minutes=1))
    late = await submit(client, tokens, contest_id, "boris", "Поздняя")
    clock.set(SUBMISSION_END)
    await vote(client, tokens["vera"], late)
    await vote(client, tokens["gleb"], late)
    await vote(client, tokens["vera"], early)
    clock.set(VOTING_END)

    assert (await view(client, tokens, contest_id, "anna"))["winner_idea_id"] == late


async def test_no_votes_means_earliest_idea_wins(client, tokens, contest_id, clock):
    """Решение пользователя: правило ничьей применяется и при нуле голосов (D-008)."""
    early = await submit(client, tokens, contest_id, "boris", "Ранняя")
    clock.advance(timedelta(minutes=1))
    await submit(client, tokens, contest_id, "anna", "Поздняя")
    clock.set(VOTING_END)

    snap = await view(client, tokens, contest_id, "organizer")
    assert snap["winner_idea_id"] == early
    assert [i["votes_count"] for i in snap["ideas"]] == [0, 0]


async def test_no_ideas_means_no_winner(client, tokens, contest_id, clock):
    clock.set(VOTING_END)
    snap = await view(client, tokens, contest_id, "anna")
    assert snap["ideas"] == []
    assert snap["winner_idea_id"] is None


async def test_revoked_votes_do_not_count_in_result(client, tokens, contest_id, clock):
    a = await submit(client, tokens, contest_id, "anna", "A")
    clock.advance(timedelta(minutes=1))
    b = await submit(client, tokens, contest_id, "boris", "B")
    clock.set(SUBMISSION_END)
    await vote(client, tokens["vera"], b)
    await vote(client, tokens["gleb"], b)
    await vote(client, tokens["vera"], a)
    await revoke(client, tokens["vera"], b)
    await revoke(client, tokens["gleb"], b)
    clock.set(VOTING_END)

    snap = await view(client, tokens, contest_id, "anna")
    assert snap["winner_idea_id"] == a
    assert [(i["title"], i["votes_count"]) for i in snap["ideas"]] == [("A", 1), ("B", 0)]


# --- число проголосовавших --------------------------------------------------


async def test_voters_count_counts_people_not_votes(client, tokens, contest_id, clock):
    a = await submit(client, tokens, contest_id, "anna", "A")
    b = await submit(client, tokens, contest_id, "boris", "B")
    c = await submit(client, tokens, contest_id, "boris", "C")
    clock.set(SUBMISSION_END)

    async def stats() -> dict:
        return (await view(client, tokens, contest_id, "organizer"))["stats"]

    assert (await stats())["voters_count"] == 0
    await vote(client, tokens["anna"], b)
    await vote(client, tokens["anna"], c)  # тот же человек, второй голос
    await vote(client, tokens["vera"], a)
    await vote(client, tokens["vera"], b)
    await vote(client, tokens["vera"], c)
    assert await stats() == {
        "participants_count": 4,
        "ideas_count": 3,
        "voters_count": 2,
        "votes_count": 5,
    }

    await revoke(client, tokens["anna"], b)
    await revoke(client, tokens["anna"], c)  # anna отозвала все голоса — больше не считается
    assert (await stats())["voters_count"] == 1
    assert (await stats())["votes_count"] == 3
