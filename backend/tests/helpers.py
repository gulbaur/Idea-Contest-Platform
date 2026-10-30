"""Вспомогательные функции тестов."""

from datetime import UTC, datetime

from httpx import AsyncClient

# Пароль демо-аккаунтов в тестах отличается от публичного, чтобы тесты не зависели от .env.
TEST_PASSWORD = "test-password"
# Произвольный фиксированный момент «сейчас» для тестов.
T0 = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


async def login(client: AsyncClient, user_login: str, password: str = TEST_PASSWORD) -> str:
    """Входит под пользователем и возвращает токен. Каждый вызов — новая сессия («вкладка»)."""
    response = await client.post("/api/auth/login", json={"login": user_login, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
