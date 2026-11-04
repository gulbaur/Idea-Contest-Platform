"""Повторы с тем же `client_request_id` (D-031, D-053; REVIEW Г2, Г5).

Идентификатор запроса означает «это та же самая отправка формы». Поэтому:
- тот же запрос ещё раз → тот же объект, 200;
- тот же идентификатор с другими данными или в другом конкурсе → 409, ничего не создаётся;
- исход не зависит от того, пришли запросы по очереди или одновременно.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import delete, func, select

from app.models import Contest, Idea
from tests.helpers import auth, create_contest, iso, login, snapshot, submit_idea, SUBMISSION_END, VOTING_END

pytestmark = pytest.mark.usefixtures("demo_users")

ROUNDS = 8  # гонки повторяем: порядок «кто первый» каждый раз решает планировщик


@pytest.fixture
async def two_contests(client, user_ids) -> tuple[dict, dict]:
    org = await login(client, "organizer")
    participants = [user_ids[u] for u in ("anna", "boris")]
    first = await create_contest(client, org, topic="Первый", participants=participants)
    second = await create_contest(client, org, topic="Второй", participants=participants)
    return first, second


async def own_ideas(client, token, contest_id) -> list[dict]:
    return [i for i in (await snapshot(client, token, contest_id)).json()["ideas"] if i["is_mine"]]


async def count(app, model) -> int:
    async with app.state.sessionmaker() as db:
        return await db.scalar(select(func.count()).select_from(model))


# --- идеи: другой конкурс ----------------------------------------------------


async def test_same_request_id_in_another_contest_is_rejected(client, two_contests, app):
    first, second = two_contests
    anna = await login(client, "anna")
    request_id = str(uuid.uuid4())
    created = await submit_idea(client, anna, first["id"], "В первый", client_request_id=request_id)
    revision_before = (await snapshot(client, anna, second["id"])).json()["revision"]

    response = await submit_idea(client, anna, second["id"], "Во второй", client_request_id=request_id)

    assert created.status_code == 201
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "request_id_reused"
    assert await own_ideas(client, anna, second["id"]) == []
    assert [i["title"] for i in await own_ideas(client, anna, first["id"])] == ["В первый"]
    assert (await snapshot(client, anna, second["id"])).json()["revision"] == revision_before


async def test_parallel_same_request_id_in_two_contests(client, two_contests, app):
    """Одновременно: ровно одна идея — в том конкурсе, куда её и отправили; второй — 409.

    Раньше проигравший запрос молча получал 200 с идеей из чужого конкурса.
    """
    first, second = two_contests
    anna = await login(client, "anna")

    for _ in range(ROUNDS):
        request_id = str(uuid.uuid4())
        responses = await asyncio.gather(
            submit_idea(client, anna, first["id"], "В первый", client_request_id=request_id),
            submit_idea(client, anna, second["id"], "Во второй", client_request_id=request_id),
        )
        assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]
        winner_contest = first if responses[0].status_code == 201 else second
        loser_contest = second if winner_contest is first else first
        idea = next(r for r in responses if r.status_code == 201).json()
        assert idea["id"] in {i["id"] for i in await own_ideas(client, anna, winner_contest["id"])}
        assert idea["id"] not in {i["id"] for i in await own_ideas(client, anna, loser_contest["id"])}

    assert await count(app, Idea) == ROUNDS


# --- идеи: другой текст в том же конкурсе (Г2) --------------------------------


async def test_same_request_id_with_other_text_is_rejected(client, two_contests, app):
    first, _ = two_contests
    anna = await login(client, "anna")
    request_id = str(uuid.uuid4())
    await submit_idea(client, anna, first["id"], "Первая", "Текст", client_request_id=request_id)

    response = await submit_idea(client, anna, first["id"], "Совсем другая", "Текст", client_request_id=request_id)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "request_id_reused"
    assert [i["title"] for i in await own_ideas(client, anna, first["id"])] == ["Первая"]


async def test_parallel_same_request_id_with_other_text(client, two_contests, app):
    first, _ = two_contests
    anna = await login(client, "anna")

    for _ in range(ROUNDS):
        request_id = str(uuid.uuid4())
        responses = await asyncio.gather(
            submit_idea(client, anna, first["id"], "Вариант А", client_request_id=request_id),
            submit_idea(client, anna, first["id"], "Вариант Б", client_request_id=request_id),
        )
        assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]

    assert await count(app, Idea) == ROUNDS


async def test_replay_of_original_after_edit_returns_current_idea(client, two_contests):
    """Старый повтор подачи после правки — это всё ещё повтор, а не новая идея."""
    first, _ = two_contests
    anna = await login(client, "anna")
    request_id = str(uuid.uuid4())
    idea = (await submit_idea(client, anna, first["id"], "Черновик", "Текст", client_request_id=request_id)).json()
    edited = await client.put(
        f"/api/ideas/{idea['id']}",
        json={"title": "Чистовик", "description": "Текст", "version": 1},
        headers=auth(anna),
    )
    assert edited.status_code == 200

    replay = await submit_idea(client, anna, first["id"], "Черновик", "Текст", client_request_id=request_id)

    assert replay.status_code == 200
    assert (replay.json()["id"], replay.json()["title"]) == (idea["id"], "Чистовик")


# --- идеи: ответ не перечитывает идею после фиксации (Г5) ----------------------


async def test_submit_response_survives_immediate_delete(client, two_contests, app, monkeypatch):
    """Другая вкладка удалила идею между фиксацией и ответом — ответ всё равно корректный."""
    first, _ = two_contests
    anna = await login(client, "anna")
    hub = app.state.hub
    original = hub.contest_changed

    async def delete_right_after_commit(contest_id, revision, **kwargs):
        async with app.state.sessionmaker() as db:
            await db.execute(delete(Idea))
            await db.commit()
        await original(contest_id, revision, **kwargs)

    monkeypatch.setattr(hub, "contest_changed", delete_right_after_commit)

    response = await submit_idea(client, anna, first["id"], "Мимолётная")

    assert response.status_code == 201, response.text
    assert response.json()["title"] == "Мимолётная"


# --- конкурсы ----------------------------------------------------------------


def contest_payload(request_id: str, topic: str) -> dict:
    return {
        "topic": topic,
        "submission_deadline": iso(SUBMISSION_END),
        "voting_deadline": iso(VOTING_END),
        "client_request_id": request_id,
    }


async def test_same_request_id_with_other_contest_data_is_rejected(client, app):
    org = await login(client, "organizer")
    request_id = str(uuid.uuid4())
    first = await client.post("/api/contests", json=contest_payload(request_id, "Первый"), headers=auth(org))

    other = await client.post("/api/contests", json=contest_payload(request_id, "Другой"), headers=auth(org))
    same = await client.post("/api/contests", json=contest_payload(request_id, "Первый"), headers=auth(org))

    assert first.status_code == 201
    assert other.status_code == 409
    assert other.json()["detail"]["code"] == "request_id_reused"
    assert (same.status_code, same.json()["id"]) == (200, first.json()["id"])
    assert await count(app, Contest) == 1


async def test_parallel_create_with_same_request_id_and_other_data(client, app):
    org = await login(client, "organizer")

    for _ in range(ROUNDS):
        request_id = str(uuid.uuid4())
        responses = await asyncio.gather(
            client.post("/api/contests", json=contest_payload(request_id, "А"), headers=auth(org)),
            client.post("/api/contests", json=contest_payload(request_id, "Б"), headers=auth(org)),
        )
        assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]

    assert await count(app, Contest) == ROUNDS


async def test_other_participants_with_same_request_id_is_rejected(client, user_ids):
    org = await login(client, "organizer")
    request_id = str(uuid.uuid4())
    payload = contest_payload(request_id, "Тема")
    first = await client.post(
        "/api/contests", json={**payload, "participant_ids": [user_ids["anna"]]}, headers=auth(org)
    )

    other = await client.post(
        "/api/contests", json={**payload, "participant_ids": [user_ids["boris"]]}, headers=auth(org)
    )
    reordered = await client.post(
        "/api/contests", json={**payload, "participant_ids": [user_ids["anna"], user_ids["anna"]]}, headers=auth(org)
    )

    assert first.status_code == 201
    assert other.status_code == 409
    assert reordered.status_code == 200  # тот же набор участников — это повтор
