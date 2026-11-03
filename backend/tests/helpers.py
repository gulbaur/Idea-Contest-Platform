"""Вспомогательные функции тестов."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

# Пароль демо-аккаунтов в тестах отличается от публичного, чтобы тесты не зависели от .env.
TEST_PASSWORD = "test-password"
# Произвольный фиксированный момент «сейчас» для тестов.
T0 = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
# Сроки конкурса по умолчанию в тестах: подача до T0+1 ч, голосование до T0+2 ч.
SUBMISSION_END = T0 + timedelta(hours=1)
VOTING_END = T0 + timedelta(hours=2)


async def login(client: AsyncClient, user_login: str, password: str = TEST_PASSWORD) -> str:
    """Входит под пользователем и возвращает токен. Каждый вызов — новая сессия («вкладка»)."""
    response = await client.post("/api/auth/login", json={"login": user_login, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def iso(moment: datetime) -> str:
    return moment.isoformat()


async def create_contest(
    client: AsyncClient,
    organizer_token: str,
    *,
    topic: str = "Как улучшить офис",
    submission_deadline: datetime = SUBMISSION_END,
    voting_deadline: datetime = VOTING_END,
    participants: list[int] | None = None,
) -> dict:
    payload = {
        "topic": topic,
        "submission_deadline": iso(submission_deadline),
        "voting_deadline": iso(voting_deadline),
        "client_request_id": str(uuid.uuid4()),
    }
    if participants is not None:
        payload["participant_ids"] = participants
    response = await client.post("/api/contests", json=payload, headers=auth(organizer_token))
    assert response.status_code == 201, response.text
    return response.json()


async def submit_idea(
    client: AsyncClient,
    token: str,
    contest_id: int,
    title: str = "Идея",
    description: str = "Описание идеи",
    client_request_id: str | None = None,
):
    """Подаёт идею и возвращает ответ целиком (тест сам проверяет код)."""
    return await client.post(
        f"/api/contests/{contest_id}/ideas",
        json={
            "title": title,
            "description": description,
            "client_request_id": client_request_id or str(uuid.uuid4()),
        },
        headers=auth(token),
    )


async def snapshot(client: AsyncClient, token: str, contest_id: int):
    return await client.get(f"/api/contests/{contest_id}", headers=auth(token))


async def vote(client: AsyncClient, token: str, idea_id: int):
    return await client.post(f"/api/ideas/{idea_id}/vote", headers=auth(token))


async def revoke(client: AsyncClient, token: str, idea_id: int):
    return await client.delete(f"/api/ideas/{idea_id}/vote", headers=auth(token))


class Tab:
    """Одна вкладка браузера: своё соединение WebSocket."""

    def __init__(self, ws) -> None:
        self.ws = ws
        self.ready: dict | None = None

    async def next(self, timeout: float = 2.0) -> dict:
        return json.loads(await asyncio.wait_for(self.ws.recv(), timeout))

    async def expect_nothing(self) -> None:
        await self.ws.send(json.dumps({"type": "ping"}))
        assert await self.next() == {"type": "pong"}

    async def close_code(self) -> int:
        await asyncio.wait_for(self.ws.wait_closed(), 2.0)
        return self.ws.close_code
