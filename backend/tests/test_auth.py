"""Вход, выход, серверная идентичность и независимые сессии вкладок (P1, P2, G5)."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models import User, UserSession
from app.security import hash_session_token
from tests.helpers import T0, TEST_PASSWORD, auth, login

pytestmark = pytest.mark.usefixtures("demo_users")


async def test_login_returns_token_user_and_expiry(client):
    response = await client.post(
        "/api/auth/login", json={"login": "organizer", "password": TEST_PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["token"]) >= 40
    assert body["user"]["login"] == "organizer"
    assert body["user"]["role"] == "organizer"
    assert "password_hash" not in body["user"]
    assert body["expires_at"].startswith((T0 + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S"))


async def test_login_is_case_and_space_insensitive_for_login(client):
    token = await login(client, "  ANNA ")
    me = await client.get("/api/auth/me", headers=auth(token))
    assert me.json()["login"] == "anna"


@pytest.mark.parametrize(
    "credentials",
    [
        {"login": "anna", "password": "wrong-password"},
        {"login": "nobody", "password": TEST_PASSWORD},
    ],
    ids=["wrong-password", "unknown-login"],
)
async def test_login_rejects_bad_credentials_with_same_message(client, credentials):
    response = await client.post("/api/auth/login", json=credentials)

    assert response.status_code == 401
    # Одинаковый ответ: по нему нельзя понять, существует ли логин.
    assert response.json() == {"detail": "Неверный логин или пароль"}


async def test_login_validates_payload(client):
    response = await client.post("/api/auth/login", json={"login": "", "password": ""})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer not-a-real-token"},
        {"Authorization": "Basic YW5uYTp0ZXN0"},
        {"Authorization": "Bearer"},
    ],
    ids=["no-header", "unknown-token", "wrong-scheme", "empty-token"],
)
async def test_me_requires_valid_token(client, headers):
    response = await client.get("/api/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Требуется вход"}


async def test_me_returns_user_of_the_session(client):
    token = await login(client, "boris")
    response = await client.get("/api/auth/me", headers=auth(token))

    assert response.status_code == 200
    assert response.json()["login"] == "boris"
    assert response.json()["role"] == "employee"


async def test_client_cannot_spoof_identity_or_role(client, app):
    """Роль и пользователь определяются только по токену, а не по данным клиента."""
    async with app.state.sessionmaker() as db:
        organizer_id = await db.scalar(select(User.id).where(User.login == "organizer"))

    # Лишнее поле role при входе игнорируется.
    response = await client.post(
        "/api/auth/login",
        json={"login": "anna", "password": TEST_PASSWORD, "role": "organizer", "id": organizer_id},
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "employee"
    token = response.json()["token"]

    # Попытки подставить чужой id или роль через заголовки и параметры не действуют.
    response = await client.get(
        "/api/auth/me",
        params={"user_id": organizer_id, "role": "organizer"},
        headers={**auth(token), "X-User-Id": str(organizer_id), "X-Role": "organizer"},
    )
    assert response.status_code == 200
    assert response.json()["login"] == "anna"
    assert response.json()["role"] == "employee"


async def test_token_and_password_are_not_stored_in_plain_text(client, app):
    token = await login(client, "vera")

    async with app.state.sessionmaker() as db:
        stored_hash = await db.scalar(select(UserSession.token_hash))
        password_hash = await db.scalar(select(User.password_hash).where(User.login == "vera"))

    assert stored_hash != token
    assert stored_hash == hash_session_token(token)
    assert TEST_PASSWORD not in password_hash
    assert password_hash.startswith("scrypt$")


async def test_session_expires_exactly_at_expires_at(client, clock):
    token = await login(client, "gleb")

    clock.advance(timedelta(hours=24) - timedelta(seconds=1))
    assert (await client.get("/api/auth/me", headers=auth(token))).status_code == 200

    clock.advance(timedelta(seconds=1))  # ровно момент истечения
    assert (await client.get("/api/auth/me", headers=auth(token))).status_code == 401


async def test_two_tabs_of_same_user_are_independent_sessions(client, app):
    """Две вкладки одного пользователя: выход в одной не выкидывает другую."""
    tab_a = await login(client, "dina")
    tab_b = await login(client, "dina")
    assert tab_a != tab_b

    response = await client.post("/api/auth/logout", headers=auth(tab_a))
    assert response.status_code == 204

    assert (await client.get("/api/auth/me", headers=auth(tab_a))).status_code == 401
    assert (await client.get("/api/auth/me", headers=auth(tab_b))).status_code == 200
    async with app.state.sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(UserSession)) == 1


async def test_two_tabs_of_different_users_do_not_affect_each_other(client):
    """Участник и организатор в двух вкладках: вход во второй не меняет пользователя первой."""
    participant_tab = await login(client, "anna")
    organizer_tab = await login(client, "organizer")

    participant = await client.get("/api/auth/me", headers=auth(participant_tab))
    organizer = await client.get("/api/auth/me", headers=auth(organizer_tab))

    assert participant.json()["login"] == "anna"
    assert organizer.json()["login"] == "organizer"


async def test_logout_requires_token(client):
    assert (await client.post("/api/auth/logout")).status_code == 401


async def test_repeated_logout_with_same_token_is_rejected(client):
    token = await login(client, "boris")
    assert (await client.post("/api/auth/logout", headers=auth(token))).status_code == 204
    assert (await client.post("/api/auth/logout", headers=auth(token))).status_code == 401


async def test_login_removes_expired_sessions_of_the_user(client, app, clock):
    old = await login(client, "anna")
    other_user = await login(client, "boris")
    clock.advance(timedelta(hours=25))  # обе сессии истекли
    fresh = await login(client, "anna")

    async with app.state.sessionmaker() as db:
        hashes = set((await db.scalars(select(UserSession.token_hash))).all())
    assert hash_session_token(old) not in hashes  # истёкшая сессия Анны удалена
    assert hash_session_token(fresh) in hashes
    # Чужие сессии вход Анны не трогает: они удалятся при входе своего владельца.
    assert hash_session_token(other_user) in hashes


async def test_demo_endpoint_lists_demo_accounts_in_demo_mode(client, app):
    app.state.settings.seed_demo_data = True
    body = (await client.get("/api/auth/demo")).json()

    assert body["enabled"] is True
    assert body["password"] == TEST_PASSWORD
    assert [a["login"] for a in body["accounts"]] == ["organizer", "anna", "boris", "vera", "gleb", "dina"]
    assert body["accounts"][0] == {"login": "organizer", "display_name": "Организатор", "role": "organizer"}


async def test_demo_endpoint_reveals_nothing_outside_demo_mode(client, app):
    app.state.settings.seed_demo_data = False
    assert (await client.get("/api/auth/demo")).json() == {"enabled": False, "password": None, "accounts": []}
