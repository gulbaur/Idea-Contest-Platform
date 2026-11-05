"""Настройки вида у пользователя на сервере (D-060)."""

import pytest

from tests.helpers import auth, login

pytestmark = pytest.mark.usefixtures("demo_users")

DEFAULTS = {"theme": "system", "font": "inter", "locale": "ru", "text_size": "medium"}


async def test_login_and_me_return_default_preferences(client):
    response = await client.post("/api/auth/login", json={"login": "anna", "password": "test-password"})
    assert response.json()["user"]["preferences"] == DEFAULTS
    me = await client.get("/api/auth/me", headers=auth(response.json()["token"]))
    assert me.json()["preferences"] == DEFAULTS


async def test_preferences_follow_the_user_into_every_tab(client):
    first_tab = await login(client, "anna")
    response = await client.patch(
        "/api/auth/me/preferences", json={"theme": "dark", "font": "golos"}, headers=auth(first_tab)
    )
    assert response.status_code == 200
    assert response.json()["preferences"] == {"theme": "dark", "font": "golos", "locale": "ru", "text_size": "medium"}

    # Новая вкладка (новый вход) того же пользователя — те же настройки.
    second_tab = await login(client, "anna")
    me = await client.get("/api/auth/me", headers=auth(second_tab))
    assert me.json()["preferences"] == {"theme": "dark", "font": "golos", "locale": "ru", "text_size": "medium"}


async def test_only_sent_fields_change(client):
    token = await login(client, "anna")
    await client.patch("/api/auth/me/preferences", json={"theme": "light"}, headers=auth(token))
    response = await client.patch("/api/auth/me/preferences", json={"font": "plex"}, headers=auth(token))
    assert response.json()["preferences"] == {"theme": "light", "font": "plex", "locale": "ru", "text_size": "medium"}


async def test_preferences_of_one_user_do_not_touch_another(client):
    """Две вкладки одного браузера под разными пользователями — у каждого свои настройки."""
    anna = await login(client, "anna")
    boris = await login(client, "boris")
    await client.patch("/api/auth/me/preferences", json={"theme": "dark"}, headers=auth(anna))
    me = await client.get("/api/auth/me", headers=auth(boris))
    assert me.json()["preferences"] == DEFAULTS


@pytest.mark.parametrize(
    "payload",
    [
        {"theme": "pink"},
        {"font": "comic-sans"},
        {"locale": "de"},
        {"text_size": "huge"},
        {"theme": None, "role": "organizer"},  # лишние поля, например роль, не принимаются
        {"display_name": "Хакер"},
    ],
)
async def test_unknown_values_and_fields_are_rejected(client, payload):
    token = await login(client, "anna")
    response = await client.patch("/api/auth/me/preferences", json=payload, headers=auth(token))
    assert response.status_code == 422
    me = await client.get("/api/auth/me", headers=auth(token))
    assert me.json()["role"] == "employee"
    assert me.json()["display_name"] == "Анна Смирнова"
    assert me.json()["preferences"] == DEFAULTS


async def test_preferences_require_login(client):
    assert (await client.patch("/api/auth/me/preferences", json={"theme": "dark"})).status_code == 401


async def test_text_size_is_saved_for_the_user(client):
    """Размер текста (D-066) — как и остальные настройки, у пользователя на сервере."""
    first = await login(client, "vera")
    changed = await client.patch("/api/auth/me/preferences", json={"text_size": "large"}, headers=auth(first))
    assert changed.json()["preferences"]["text_size"] == "large"
    second = await login(client, "vera")  # другая вкладка или устройство
    assert (await client.get("/api/auth/me", headers=auth(second))).json()["preferences"]["text_size"] == "large"
