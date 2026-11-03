"""Ввод, который раньше приводил к 500, и вход без простоя соединения БД (D-038).

Найдено при проверке качества (docs/REVIEW.md: A1–A3, В1).
"""

import json
import uuid

import pytest
from sqlalchemy import func, select

import app.api.auth as auth_module
from app.models import Contest, Idea
from tests.helpers import SUBMISSION_END, VOTING_END, auth, create_contest, iso, login, submit_idea

pytestmark = pytest.mark.usefixtures("demo_users")

# Символ NUL и одиночный суррогат: PostgreSQL и драйвер не могут их сохранить.
BAD_TEXTS = pytest.mark.parametrize("bad", ["a\x00b", "a\ud800b"], ids=["nul", "surrogate"])
MAX_ID = 2_147_483_647


async def send_json(client, method: str, url: str, body: dict, token: str | None = None):
    # json.dumps экранирует символы как \uXXXX; httpx сам такой текст отправить не может —
    # одиночный суррогат не кодируется в UTF-8.
    headers = {"Content-Type": "application/json"}
    if token:
        headers.update(auth(token))
    return await client.request(method, url, content=json.dumps(body), headers=headers)


@BAD_TEXTS
async def test_login_with_unstorable_characters_is_422(client, bad):
    response = await send_json(client, "POST", "/api/auth/login", {"login": bad, "password": "x"})
    assert response.status_code == 422


@BAD_TEXTS
@pytest.mark.parametrize("field", ["title", "description"])
async def test_idea_with_unstorable_characters_is_422(client, app, bad, field):
    org, anna = await login(client, "organizer"), await login(client, "anna")
    contest = await create_contest(client, org)
    body = {"title": "Идея", "description": "Описание", "client_request_id": str(uuid.uuid4())}
    body[field] = bad

    response = await send_json(client, "POST", f"/api/contests/{contest['id']}/ideas", body, anna)

    assert response.status_code == 422
    async with app.state.sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(Idea)) == 0


@BAD_TEXTS
async def test_idea_edit_with_unstorable_characters_is_422(client, bad):
    org, anna = await login(client, "organizer"), await login(client, "anna")
    contest = await create_contest(client, org)
    idea = (await submit_idea(client, anna, contest["id"])).json()

    body = {"title": bad, "description": "Описание", "version": idea["version"]}
    response = await send_json(client, "PUT", f"/api/ideas/{idea['id']}", body, anna)

    assert response.status_code == 422


@BAD_TEXTS
async def test_contest_topic_with_unstorable_characters_is_422(client, app, bad):
    org = await login(client, "organizer")
    body = {
        "topic": bad,
        "submission_deadline": iso(SUBMISSION_END),
        "voting_deadline": iso(VOTING_END),
        "client_request_id": str(uuid.uuid4()),
    }

    response = await send_json(client, "POST", "/api/contests", body, org)

    assert response.status_code == 422
    async with app.state.sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(Contest)) == 0


async def test_ordinary_unicode_is_still_accepted(client):
    """Кириллица, эмодзи (составные символы), переводы строк и табуляция — обычный текст."""
    org, anna = await login(client, "organizer"), await login(client, "anna")
    contest = await create_contest(client, org, topic="Офис 🏢")
    response = await submit_idea(client, anna, contest["id"], "Кофе ☕", "Строка 1\nСтрока 2\tтаб")
    assert response.status_code == 201
    assert response.json()["title"] == "Кофе ☕"


@pytest.mark.parametrize("number", [0, -1, MAX_ID + 1, 99_999_999_999])
async def test_out_of_range_ids_are_422_not_500(client, number):
    anna = await login(client, "anna")
    headers = auth(anna)
    responses = [
        await client.get(f"/api/contests/{number}", headers=headers),
        await client.post(
            f"/api/contests/{number}/ideas",
            json={"title": "a", "description": "b", "client_request_id": str(uuid.uuid4())},
            headers=headers,
        ),
        await client.put(
            f"/api/ideas/{number}",
            json={"title": "a", "description": "b", "version": 1},
            headers=headers,
        ),
        await client.delete(f"/api/ideas/{number}", headers=headers),
        await client.post(f"/api/ideas/{number}/vote", headers=headers),
        await client.delete(f"/api/ideas/{number}/vote", headers=headers),
    ]
    assert [r.status_code for r in responses] == [422] * len(responses)


async def test_largest_valid_id_is_plain_404(client):
    anna = await login(client, "anna")
    assert (await client.get(f"/api/contests/{MAX_ID}", headers=auth(anna))).status_code == 404
    assert (await client.post(f"/api/ideas/{MAX_ID}/vote", headers=auth(anna))).status_code == 404


async def test_login_releases_db_connection_while_checking_password(client, app, monkeypatch):
    """Пока scrypt проверяет пароль, вход не занимает соединение из пула (REVIEW В1)."""
    pool = app.state.engine.pool
    seen: list[int] = []
    original = auth_module.verify_password

    def spy(password: str, stored: str) -> bool:
        seen.append(pool.checkedout())
        return original(password, stored)

    monkeypatch.setattr(auth_module, "verify_password", spy)
    await login(client, "anna")
    response = await client.post("/api/auth/login", json={"login": "nobody", "password": "x"})

    assert response.status_code == 401
    assert seen == [0, 0]
