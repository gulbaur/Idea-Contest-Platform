"""Создание конкурса, список участников, список конкурсов (F1, D-009, D-031, D-032)."""

import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models import Contest, ContestParticipant
from tests.helpers import (
    SUBMISSION_END,
    T0,
    VOTING_END,
    auth,
    create_contest,
    iso,
    login,
    snapshot,
)

pytestmark = pytest.mark.usefixtures("demo_users")

EMPLOYEES = ["anna", "boris", "vera", "gleb", "dina"]


def contest_payload(**overrides) -> dict:
    payload = {
        "topic": "Как улучшить офис",
        "submission_deadline": iso(SUBMISSION_END),
        "voting_deadline": iso(VOTING_END),
        "client_request_id": str(uuid.uuid4()),
    }
    payload.update(overrides)
    return payload


async def test_organizer_creates_contest_with_all_employees_by_default(client):
    org = await login(client, "organizer")

    contest = await create_contest(client, org)

    assert contest["topic"] == "Как улучшить офис"
    assert contest["phase"] == "submission"
    snap = (await snapshot(client, org, contest["id"])).json()
    assert snap["stats"] == {"participants_count": len(EMPLOYEES), "ideas_count": 0}
    assert snap["revision"] == 1


async def test_explicit_participants_limit_who_sees_the_contest(client, user_ids):
    org = await login(client, "organizer")
    contest = await create_contest(
        client, org, participants=[user_ids["anna"], user_ids["boris"]]
    )

    anna, dina = await login(client, "anna"), await login(client, "dina")

    assert (await snapshot(client, anna, contest["id"])).status_code == 200
    # Не участник: конкурс для него «не существует» (D-030).
    response = await snapshot(client, dina, contest["id"])
    assert response.status_code == 404
    assert [c["id"] for c in (await client.get("/api/contests", headers=auth(anna))).json()] == [
        contest["id"]
    ]
    assert (await client.get("/api/contests", headers=auth(dina))).json() == []


async def test_only_organizer_creates_contests(client):
    anna = await login(client, "anna")
    response = await client.post("/api/contests", json=contest_payload(), headers=auth(anna))
    assert response.status_code == 403
    assert (await client.post("/api/contests", json=contest_payload())).status_code == 401


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"submission_deadline": iso(T0)}, "в будущем"),  # ровно «сейчас» — уже не будущее
        ({"submission_deadline": iso(T0 - timedelta(minutes=1))}, "в будущем"),
        ({"voting_deadline": iso(SUBMISSION_END)}, "позже"),
        ({"voting_deadline": iso(SUBMISSION_END - timedelta(minutes=1))}, "позже"),
        ({"submission_deadline": "2026-01-15T10:00:00"}, None),  # без часового пояса
        ({"topic": "   "}, None),
        ({"topic": "т" * 201}, None),
        ({"participant_ids": []}, None),
        ({"participant_ids": [999]}, "только сотрудники"),
    ],
    ids=[
        "submission-now",
        "submission-past",
        "voting-equals-submission",
        "voting-before-submission",
        "naive-datetime",
        "blank-topic",
        "long-topic",
        "empty-participants",
        "unknown-participant",
    ],
)
async def test_contest_validation(client, overrides, fragment):
    org = await login(client, "organizer")
    response = await client.post("/api/contests", json=contest_payload(**overrides), headers=auth(org))
    assert response.status_code == 422
    if fragment:
        assert fragment in response.json()["detail"]


async def test_organizer_cannot_be_a_participant(client, user_ids):
    org = await login(client, "organizer")
    response = await client.post(
        "/api/contests",
        json=contest_payload(participant_ids=[user_ids["anna"], user_ids["organizer"]]),
        headers=auth(org),
    )
    assert response.status_code == 422


async def test_repeated_create_request_returns_the_same_contest(client, app):
    org = await login(client, "organizer")
    payload = contest_payload()

    first = await client.post("/api/contests", json=payload, headers=auth(org))
    second = await client.post("/api/contests", json=payload, headers=auth(org))

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    async with app.state.sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(Contest)) == 1


async def test_parallel_identical_create_requests_create_one_contest(client, app):
    """Одновременные одинаковые запросы (независимые соединения БД) — один конкурс."""
    org = await login(client, "organizer")
    payload = contest_payload()

    responses = await asyncio.gather(
        *(client.post("/api/contests", json=payload, headers=auth(org)) for _ in range(5))
    )

    assert sorted(r.status_code for r in responses) == [200, 200, 200, 200, 201]
    assert len({r.json()["id"] for r in responses}) == 1
    async with app.state.sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(Contest)) == 1
        assert await db.scalar(select(func.count()).select_from(ContestParticipant)) == len(
            EMPLOYEES
        )


async def test_contest_list_phase_follows_server_time(client, clock):
    org = await login(client, "organizer")
    await create_contest(client, org)

    async def phase() -> str:
        return (await client.get("/api/contests", headers=auth(org))).json()[0]["phase"]

    assert await phase() == "submission"
    clock.set(SUBMISSION_END)
    assert await phase() == "voting"
    clock.set(VOTING_END)
    assert await phase() == "finished"


async def test_employee_list_is_for_organizer_only(client):
    org, anna = await login(client, "organizer"), await login(client, "anna")

    response = await client.get("/api/users", headers=auth(org))
    assert response.status_code == 200
    assert sorted(u["login"] for u in response.json()) == sorted(EMPLOYEES)
    assert (await client.get("/api/users", headers=auth(anna))).status_code == 403


async def test_unknown_contest_is_404(client):
    org = await login(client, "organizer")
    assert (await snapshot(client, org, 12345)).status_code == 404
