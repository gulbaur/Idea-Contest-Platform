"""Подача, правка и удаление идей: права, сроки, повторы (F2, F3, F10, D-029 … D-031)."""

import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models import Idea
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

TICK = timedelta(microseconds=1)


@pytest.fixture
async def contest(client, user_ids) -> dict:
    """Конкурс с участниками anna, boris, vera (dina — не участник)."""
    org = await login(client, "organizer")
    return await create_contest(
        client, org, participants=[user_ids[u] for u in ("anna", "boris", "vera")]
    )


async def ideas_count(app) -> int:
    async with app.state.sessionmaker() as db:
        return await db.scalar(select(func.count()).select_from(Idea))


async def edit(client, token, idea_id, title, description, version):
    return await client.put(
        f"/api/ideas/{idea_id}",
        json={"title": title, "description": description, "version": version},
        headers=auth(token),
    )


# --- подача -----------------------------------------------------------------


async def test_participant_submits_idea(client, contest):
    anna = await login(client, "anna")

    response = await submit_idea(client, anna, contest["id"], "  Велопарковка  ", "Навес у входа")

    assert response.status_code == 201
    idea = response.json()
    assert idea["title"] == "Велопарковка"  # пробелы по краям обрезаны
    assert idea["version"] == 1
    assert idea["is_mine"] is True
    assert idea["author"] is None
    assert idea["submitted_at"].startswith(T0.strftime("%Y-%m-%dT%H:%M:%S"))


async def test_participant_may_submit_several_ideas(client, contest, app):
    anna = await login(client, "anna")
    assert (await submit_idea(client, anna, contest["id"], "Первая")).status_code == 201
    assert (await submit_idea(client, anna, contest["id"], "Вторая")).status_code == 201
    assert await ideas_count(app) == 2


async def test_organizer_cannot_submit(client, contest):
    org = await login(client, "organizer")
    response = await submit_idea(client, org, contest["id"])
    assert response.status_code == 403
    assert response.json()["detail"] == "Организатор не подаёт идеи"


async def test_non_participant_cannot_submit(client, contest):
    dina = await login(client, "dina")
    assert (await submit_idea(client, dina, contest["id"])).status_code == 404


@pytest.mark.parametrize(
    ("title", "description"),
    [("", "текст"), ("   ", "текст"), ("т" * 201, "текст"), ("Идея", ""), ("Идея", "о" * 5001)],
    ids=["empty-title", "blank-title", "long-title", "empty-description", "long-description"],
)
async def test_idea_validation(client, contest, title, description):
    anna = await login(client, "anna")
    response = await submit_idea(client, anna, contest["id"], title, description)
    assert response.status_code == 422


async def test_submission_closes_exactly_at_deadline(client, contest, clock, app):
    anna = await login(client, "anna")

    clock.set(SUBMISSION_END - TICK)
    assert (await submit_idea(client, anna, contest["id"], "В последний момент")).status_code == 201

    clock.set(SUBMISSION_END)
    response = await submit_idea(client, anna, contest["id"], "Опоздала")
    assert response.status_code == 409
    assert response.json()["detail"] == "Приём идей закрыт"

    clock.set(VOTING_END + timedelta(hours=1))  # в пределах 24 ч жизни сессии входа
    assert (await submit_idea(client, anna, contest["id"], "Совсем поздно")).status_code == 409
    assert await ideas_count(app) == 1


async def test_stale_page_cannot_submit_after_deadline(client, contest, clock):
    """Страница открыта до срока, форма отправлена после — сервер отклоняет."""
    anna = await login(client, "anna")
    page = await snapshot(client, anna, contest["id"])
    assert page.json()["contest"]["phase"] == "submission"

    clock.advance(timedelta(hours=1))  # пользователь «думал» час, срок прошёл
    assert (await submit_idea(client, anna, contest["id"])).status_code == 409


async def test_repeated_submit_with_same_request_id_returns_same_idea(client, contest, app):
    anna = await login(client, "anna")
    request_id = str(uuid.uuid4())

    first = await submit_idea(client, anna, contest["id"], client_request_id=request_id)
    second = await submit_idea(client, anna, contest["id"], client_request_id=request_id)

    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]
    assert await ideas_count(app) == 1


async def test_parallel_identical_submits_create_one_idea(client, contest, app):
    """Двойное нажатие / две вкладки с одной формой: независимые соединения, одна идея."""
    anna = await login(client, "anna")
    request_id = str(uuid.uuid4())

    responses = await asyncio.gather(
        *(
            submit_idea(client, anna, contest["id"], client_request_id=request_id)
            for _ in range(5)
        )
    )

    assert sorted(r.status_code for r in responses) == [200, 200, 200, 200, 201]
    assert len({r.json()["id"] for r in responses}) == 1
    assert await ideas_count(app) == 1
    org = await login(client, "organizer")
    assert (await snapshot(client, org, contest["id"])).json()["revision"] == 2


async def test_retry_after_deadline_returns_already_accepted_idea(client, contest, clock):
    anna = await login(client, "anna")
    request_id = str(uuid.uuid4())
    first = await submit_idea(client, anna, contest["id"], client_request_id=request_id)

    clock.set(SUBMISSION_END)  # ответ «потерялся», клиент повторяет запрос после срока
    retry = await submit_idea(client, anna, contest["id"], client_request_id=request_id)

    assert retry.status_code == 200
    assert retry.json()["id"] == first.json()["id"]


async def test_parallel_submits_from_different_participants_all_succeed(client, contest, app):
    tokens = [await login(client, u) for u in ("anna", "boris", "vera")]

    responses = await asyncio.gather(
        *(submit_idea(client, t, contest["id"], f"Идея {i}") for i, t in enumerate(tokens))
    )

    assert [r.status_code for r in responses] == [201, 201, 201]
    org = await login(client, "organizer")
    snap = (await snapshot(client, org, contest["id"])).json()
    assert snap["stats"]["ideas_count"] == 3
    assert snap["revision"] == 4  # 1 при создании + 3 подачи, без потерянных обновлений


# --- правка -----------------------------------------------------------------


async def test_author_edits_idea_before_deadline_keeping_submitted_at(client, contest, clock):
    anna = await login(client, "anna")
    idea = (await submit_idea(client, anna, contest["id"], "Черновик", "Текст")).json()

    clock.advance(timedelta(minutes=10))
    response = await edit(client, anna, idea["id"], "Чистовик", "Новый текст", version=1)

    assert response.status_code == 200
    edited = response.json()
    assert edited["title"] == "Чистовик"
    assert edited["version"] == 2
    assert edited["submitted_at"] == idea["submitted_at"]  # правило ничьей (D-008)
    assert edited["updated_at"] != idea["updated_at"]


async def test_edit_rejected_exactly_at_deadline_and_later(client, contest, clock):
    anna = await login(client, "anna")
    idea = (await submit_idea(client, anna, contest["id"])).json()

    clock.set(SUBMISSION_END - TICK)
    assert (await edit(client, anna, idea["id"], "Успела", "Текст", 1)).status_code == 200

    clock.set(SUBMISSION_END)
    response = await edit(client, anna, idea["id"], "Не успела", "Текст", 2)
    assert response.status_code == 409
    assert "закрыт" in response.json()["detail"]

    clock.set(VOTING_END)
    assert (await edit(client, anna, idea["id"], "Не успела", "Текст", 2)).status_code == 409


async def test_cannot_edit_someone_elses_idea(client, contest):
    anna, boris = await login(client, "anna"), await login(client, "boris")
    org = await login(client, "organizer")
    idea = (await submit_idea(client, anna, contest["id"])).json()

    # Чужая идея неотличима от несуществующей (D-030).
    assert (await edit(client, boris, idea["id"], "Взлом", "Текст", 1)).status_code == 404
    assert (await edit(client, org, idea["id"], "Взлом", "Текст", 1)).status_code == 404
    assert (await edit(client, anna, 999999, "Нет такой", "Текст", 1)).status_code == 404


async def test_stale_version_from_other_tab_is_rejected_with_current_data(client, contest):
    tab_a, tab_b = await login(client, "anna"), await login(client, "anna")
    idea = (await submit_idea(client, tab_a, contest["id"], "Исходная", "Текст")).json()

    assert (await edit(client, tab_a, idea["id"], "Из вкладки A", "Текст", 1)).status_code == 200
    # Вкладка B не видела правку и отправляет свою версию поверх версии 1.
    response = await edit(client, tab_b, idea["id"], "Из вкладки B", "Текст", 1)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["current"]["title"] == "Из вкладки A"
    assert detail["current"]["version"] == 2


async def test_repeated_identical_edit_is_idempotent(client, contest, app):
    anna = await login(client, "anna")
    idea = (await submit_idea(client, anna, contest["id"])).json()

    first = await edit(client, anna, idea["id"], "Новая", "Текст", 1)
    repeat = await edit(client, anna, idea["id"], "Новая", "Текст", 1)  # двойное нажатие

    assert (first.status_code, repeat.status_code) == (200, 200)
    assert repeat.json()["version"] == 2


# --- удаление ---------------------------------------------------------------


async def test_author_deletes_idea_during_submission(client, contest, app):
    anna = await login(client, "anna")
    idea = (await submit_idea(client, anna, contest["id"])).json()

    response = await client.delete(f"/api/ideas/{idea['id']}", headers=auth(anna))

    assert response.status_code == 204
    assert (await snapshot(client, anna, contest["id"])).json()["ideas"] == []
    assert await ideas_count(app) == 0


async def test_author_deletes_idea_during_voting_and_it_disappears_for_others(
    client, contest, clock
):
    anna, boris = await login(client, "anna"), await login(client, "boris")
    idea = (await submit_idea(client, anna, contest["id"], "Удалю")).json()
    await submit_idea(client, boris, contest["id"], "Останется")

    clock.set(SUBMISSION_END)
    assert len((await snapshot(client, boris, contest["id"])).json()["ideas"]) == 2
    assert (await client.delete(f"/api/ideas/{idea['id']}", headers=auth(anna))).status_code == 204

    titles = [i["title"] for i in (await snapshot(client, boris, contest["id"])).json()["ideas"]]
    assert titles == ["Останется"]


async def test_delete_rejected_after_final(client, contest, clock, app):
    anna = await login(client, "anna")
    idea = (await submit_idea(client, anna, contest["id"])).json()

    clock.set(VOTING_END)
    response = await client.delete(f"/api/ideas/{idea['id']}", headers=auth(anna))

    assert response.status_code == 409
    assert await ideas_count(app) == 1


async def test_cannot_delete_someone_elses_idea_and_repeat_delete_is_404(client, contest, app):
    anna, boris = await login(client, "anna"), await login(client, "boris")
    org = await login(client, "organizer")
    idea = (await submit_idea(client, anna, contest["id"])).json()

    assert (await client.delete(f"/api/ideas/{idea['id']}", headers=auth(boris))).status_code == 404
    assert (await client.delete(f"/api/ideas/{idea['id']}", headers=auth(org))).status_code == 404
    assert await ideas_count(app) == 1

    assert (await client.delete(f"/api/ideas/{idea['id']}", headers=auth(anna))).status_code == 204
    assert (await client.delete(f"/api/ideas/{idea['id']}", headers=auth(anna))).status_code == 404


async def test_revision_grows_on_each_change_but_not_on_rejected_or_repeated(client, contest, clock):
    anna, org = await login(client, "anna"), await login(client, "organizer")

    async def revision() -> int:
        return (await snapshot(client, org, contest["id"])).json()["revision"]

    assert await revision() == 1
    request_id = str(uuid.uuid4())
    idea = (await submit_idea(client, anna, contest["id"], client_request_id=request_id)).json()
    assert await revision() == 2
    await submit_idea(client, anna, contest["id"], client_request_id=request_id)  # повтор
    assert await revision() == 2
    await edit(client, anna, idea["id"], "Правка", "Текст", 1)
    assert await revision() == 3
    await edit(client, anna, idea["id"], "Правка", "Текст", 1)  # повтор той же правки
    assert await revision() == 3
    await client.delete(f"/api/ideas/{idea['id']}", headers=auth(anna))
    assert await revision() == 4
    clock.set(SUBMISSION_END)
    await submit_idea(client, anna, contest["id"])  # отклонено по сроку
    assert await revision() == 4
