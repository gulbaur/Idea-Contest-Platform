"""Сотрудники и доступ (D-062): роли, приглашение по ссылке, отключение, смена роли,
ограничение попыток входа, смена пароля, журнал действий."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import Email, User
from tests.helpers import SUBMISSION_END, TEST_PASSWORD, VOTING_END, auth, create_contest, login, submit_idea

pytestmark = pytest.mark.usefixtures("demo_users")

GOOD_PASSWORD = "длинный-пароль-2026"


async def _invite(client, admin, login_="petr", role="employee", email=None):
    response = await client.post(
        "/api/admin/users",
        json={"login": login_, "display_name": "Пётр Сидоров", "email": email or f"{login_}@example.com", "role": role},
        headers=auth(admin),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _setup(client, token, password=GOOD_PASSWORD):
    return await client.post("/api/auth/setup", json={"token": token, "password": password})


async def _staff(client, admin, login_):
    users = (await client.get("/api/admin/users", headers=auth(admin))).json()
    return next(u for u in users if u["login"] == login_)


# --- права -----------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["organizer", "anna"])
async def test_only_admin_manages_staff(client, user_ids, who):
    token = await login(client, who)
    target = user_ids["boris"]
    calls = [
        client.get("/api/admin/users", headers=auth(token)),
        client.post("/api/admin/users", json={"login": "x1", "display_name": "X", "email": "x1@example.com"}, headers=auth(token)),
        client.patch(f"/api/admin/users/{target}", json={"role": "organizer"}, headers=auth(token)),
        client.post(f"/api/admin/users/{target}/disable", headers=auth(token)),
        client.post(f"/api/admin/users/{target}/setup-link", headers=auth(token)),
        client.get("/api/admin/audit", headers=auth(token)),
    ]
    for call in calls:
        assert (await call).status_code == 403
    assert (await client.get("/api/admin/users")).status_code == 401
    me = await login(client, "boris")  # Борис не пострадал
    assert (await client.get("/api/auth/me", headers=auth(me))).json()["role"] == "employee"


async def test_admin_does_not_run_or_see_contests(client, user_ids):
    admin = await login(client, "admin")
    organizer = await login(client, "organizer")
    contest = await create_contest(client, organizer)

    assert (await client.get("/api/contests", headers=auth(admin))).json() == []
    assert (await client.get(f"/api/contests/{contest['id']}", headers=auth(admin))).status_code == 404
    created = await client.post(
        "/api/contests",
        json={
            "topic": "Тема",
            "submission_deadline": SUBMISSION_END.isoformat(),
            "voting_deadline": VOTING_END.isoformat(),
            "client_request_id": "00000000-0000-4000-8000-000000000001",
        },
        headers=auth(admin),
    )
    assert created.status_code == 403
    # В участники конкурса администратора не выбрать.
    employees = (await client.get("/api/users", headers=auth(organizer))).json()
    assert "admin" not in {e["login"] for e in employees}


# --- приглашение и первый вход ---------------------------------------------------------


async def test_invited_employee_sets_own_password_by_one_time_link(client, app):
    admin = await login(client, "admin")
    created = await _invite(client, admin)
    token = created["setup"]["token"]
    assert created["user"]["status"] == "invited"

    # До задания пароля войти нельзя — ответ тот же, что при неверном пароле.
    denied = await client.post("/api/auth/login", json={"login": "petr", "password": GOOD_PASSWORD})
    assert denied.status_code == 401
    assert denied.json()["detail"] == "Неверный логин или пароль"

    check = await client.post("/api/auth/setup/check", json={"token": token})
    assert check.json() == {"login": "petr", "display_name": "Пётр Сидоров"}

    weak = await _setup(client, token, "petr")
    assert weak.status_code == 422
    assert (await _setup(client, token, "1234567890")).status_code == 422  # слишком частый пароль

    done = await _setup(client, token)
    assert done.status_code == 200
    assert done.json()["user"]["login"] == "petr"
    me = await client.get("/api/auth/me", headers=auth(done.json()["token"]))
    assert me.json()["role"] == "employee"

    # Ссылка одноразовая; в БД хранился только хеш токена.
    assert (await _setup(client, token, "другой-пароль-2026")).status_code == 404
    async with app.state.sessionmaker() as db:
        petr = await db.scalar(select(User).where(User.login == "petr"))
    assert petr.setup_token_hash is None
    assert token not in (petr.password_hash or "")
    assert (await _staff(client, admin, "petr"))["status"] == "active"
    assert (await login(client, "petr", GOOD_PASSWORD))


async def test_setup_link_expires_after_72_hours(client, clock):
    admin = await login(client, "admin")
    token = (await _invite(client, admin))["setup"]["token"]
    clock.advance(timedelta(hours=72))
    assert (await client.post("/api/auth/setup/check", json={"token": token})).status_code == 404
    assert (await _setup(client, token)).status_code == 404


async def test_same_link_used_twice_at_once_sets_password_once(client):
    admin = await login(client, "admin")
    token = (await _invite(client, admin))["setup"]["token"]
    first, second = await asyncio.gather(_setup(client, token, "первый-пароль-2026"), _setup(client, token, "второй-пароль-2026"))
    assert sorted([first.status_code, second.status_code]) == [200, 404]


@pytest.mark.parametrize(
    "payload",
    [
        {"login": "Пётр", "display_name": "Пётр", "email": "p@example.com"},  # кириллица в логине
        {"login": "p", "display_name": "Пётр", "email": "p@example.com"},  # слишком короткий
        {"login": "petr", "display_name": "Пётр", "email": "не-почта"},
        {"login": "petr", "display_name": " ", "email": "p@example.com"},
        {"login": "petr", "display_name": "Пётр", "email": "p@example.com", "role": "superuser"},
        {"login": "petr", "display_name": "Пётр", "email": "p@example.com", "password_hash": "x"},
    ],
)
async def test_invite_rejects_bad_input(client, payload):
    admin = await login(client, "admin")
    assert (await client.post("/api/admin/users", json=payload, headers=auth(admin))).status_code == 422


async def test_invite_rejects_taken_login_and_email(client):
    admin = await login(client, "admin")
    taken_login = await client.post(
        "/api/admin/users", json={"login": "ANNA", "display_name": "Ещё Анна", "email": "new@example.com"}, headers=auth(admin)
    )
    assert taken_login.status_code == 409
    taken_email = await client.post(
        "/api/admin/users", json={"login": "anna2", "display_name": "Ещё Анна", "email": "Anna@Example.com"}, headers=auth(admin)
    )
    assert taken_email.status_code == 409


# --- отключение ------------------------------------------------------------------------


async def test_disabling_closes_access_at_once(client, user_ids, open_tab):
    admin = await login(client, "admin")
    boris = await login(client, "boris")
    tab = await open_tab(boris)

    response = await client.post(f"/api/admin/users/{user_ids['boris']}/disable", headers=auth(admin))
    assert response.json()["status"] == "disabled"

    assert await tab.close_code() == 4401  # открытая вкладка выходит сразу
    assert (await client.get("/api/auth/me", headers=auth(boris))).status_code == 401
    denied = await client.post("/api/auth/login", json={"login": "boris", "password": TEST_PASSWORD})
    assert denied.status_code == 401
    assert denied.json()["detail"] == "Неверный логин или пароль"  # без подсказки «отключён»

    await client.post(f"/api/admin/users/{user_ids['boris']}/enable", headers=auth(admin))
    assert await login(client, "boris")


async def test_disabled_employee_cannot_be_chosen_and_gets_no_letters(client, user_ids, app, clock):
    admin = await login(client, "admin")
    organizer = await login(client, "organizer")
    contest = await create_contest(client, organizer, participants=[user_ids["anna"], user_ids["boris"]])
    anna = await login(client, "anna")
    await submit_idea(client, anna, contest["id"])
    await client.post(f"/api/admin/users/{user_ids['boris']}/disable", headers=auth(admin))

    employees = {e["login"] for e in (await client.get("/api/users", headers=auth(organizer))).json()}
    assert "boris" not in employees
    rejected = await client.post(
        "/api/contests",
        json={
            "topic": "Новый",
            "submission_deadline": SUBMISSION_END.isoformat(),
            "voting_deadline": VOTING_END.isoformat(),
            "participant_ids": [user_ids["boris"]],
            "client_request_id": "00000000-0000-4000-8000-000000000002",
        },
        headers=auth(organizer),
    )
    assert rejected.status_code == 422

    clock.set(VOTING_END)
    await app.state.jobs.run_due()
    async with app.state.sessionmaker() as db:
        # Приглашение Борис получил до отключения; итогов после отключения — нет.
        recipients = set((await db.scalars(select(Email.recipient_id).where(Email.kind == "final"))).all())
    assert user_ids["anna"] in recipients
    assert user_ids["boris"] not in recipients


async def test_admin_cannot_lock_themselves_or_the_last_admin_out(client, user_ids):
    admin = await login(client, "admin")
    me = user_ids["admin"]
    assert (await client.post(f"/api/admin/users/{me}/disable", headers=auth(admin))).status_code == 409
    assert (await client.patch(f"/api/admin/users/{me}", json={"role": "employee"}, headers=auth(admin))).status_code == 409

    # Второй администратор может понизить первого, но не последнего оставшегося.
    second = await _invite(client, admin, "kira", role="admin")
    kira = (await _setup(client, second["setup"]["token"])).json()["token"]
    assert (await client.patch(f"/api/admin/users/{me}", json={"role": "employee"}, headers=auth(kira))).status_code == 200
    # Теперь Кира — единственный администратор и отключить себя не может.
    assert (await client.post(f"/api/admin/users/{second['user']['id']}/disable", headers=auth(kira))).status_code == 409


# --- смена роли ------------------------------------------------------------------------


async def test_role_cannot_change_while_participating_in_unfinished_contest(client, user_ids, clock):
    admin = await login(client, "admin")
    organizer = await login(client, "organizer")
    await create_contest(client, organizer, topic="Идущий конкурс", participants=[user_ids["anna"]])

    blocked = await client.patch(f"/api/admin/users/{user_ids['anna']}", json={"role": "organizer"}, headers=auth(admin))
    assert blocked.status_code == 409
    assert "«Идущий конкурс»" in blocked.json()["detail"]
    assert (await _staff(client, admin, "anna"))["active_contests"] == ["Идущий конкурс"]

    clock.set(VOTING_END)  # конкурс завершён — роль можно менять
    anna = await login(client, "anna")
    changed = await client.patch(f"/api/admin/users/{user_ids['anna']}", json={"role": "organizer"}, headers=auth(admin))
    assert changed.status_code == 200
    # Новая роль — новые права: прежние сессии завершены, войти нужно заново.
    assert (await client.get("/api/auth/me", headers=auth(anna))).status_code == 401
    assert (await client.get("/api/auth/me", headers=auth(await login(client, "anna")))).json()["role"] == "organizer"


@pytest.mark.parametrize("first", ["contest", "promotion"])
async def test_contest_creation_and_promotion_at_once_never_leave_organizer_as_participant(
    client, app, user_ids, monkeypatch, first
):
    """Гонка: создание конкурса с Глебом и одновременное назначение Глеба организатором.

    Пауза внутри транзакции того запроса, что начал первым, гарантирует чередование:
    без блокировки строк сотрудников оба запроса прошли бы, и организатор оказался бы
    участником идущего конкурса.
    """
    from app.api import admin as admin_api
    from app.api import contests as contests_api

    def pause_after(module, name):
        original = getattr(module, name)

        async def slow(*args, **kwargs):
            result = await original(*args, **kwargs)
            await asyncio.sleep(0.3)  # транзакция ещё открыта — второй запрос успевает начаться
            return result

        monkeypatch.setattr(module, name, slow)

    if first == "contest":
        pause_after(contests_api, "_employee_ids")
    else:
        pause_after(admin_api, "_active_contests")

    admin = await login(client, "admin")
    organizer = await login(client, "organizer")
    gleb_id = user_ids["gleb"]
    payload = {
        "topic": "Гонка",
        "submission_deadline": SUBMISSION_END.isoformat(),
        "voting_deadline": VOTING_END.isoformat(),
        "participant_ids": [gleb_id],
        "client_request_id": "00000000-0000-4000-8000-000000000100",
    }

    async def create():
        return await client.post("/api/contests", json=payload, headers=auth(organizer))

    async def promote():
        return await client.patch(f"/api/admin/users/{gleb_id}", json={"role": "organizer"}, headers=auth(admin))

    async def later(call):
        await asyncio.sleep(0.1)
        return await call()

    if first == "contest":
        created, promoted = await asyncio.gather(create(), later(promote))
        assert (created.status_code, promoted.status_code) == (201, 409)
    else:
        promoted, created = await asyncio.gather(promote(), later(create))
        assert (promoted.status_code, created.status_code) == (200, 422)

    async with app.state.sessionmaker() as db:
        gleb = await db.get(User, gleb_id)
    contests = (await client.get("/api/contests", headers=auth(organizer))).json()
    # Итог всегда согласован: организатор не может быть участником конкурса.
    assert (gleb.role == "organizer") != any(c["topic"] == "Гонка" for c in contests)


# --- ограничение попыток входа ---------------------------------------------------------


async def test_five_failures_lock_login_for_15_minutes(client, clock):
    for _ in range(5):
        r = await client.post("/api/auth/login", json={"login": "anna", "password": "неверный"})
        assert r.status_code == 401
    locked = await client.post("/api/auth/login", json={"login": "anna", "password": TEST_PASSWORD})
    assert locked.status_code == 429  # даже верный пароль — подбор остановлен
    assert locked.headers["Retry-After"] == "900"

    clock.advance(timedelta(minutes=15))
    assert await login(client, "anna")


async def test_unknown_login_is_throttled_the_same_way(client):
    """По ответу «слишком много попыток» нельзя узнать, существует ли логин."""
    for name in ("anna", "no-such-user"):
        codes = [
            (await client.post("/api/auth/login", json={"login": name, "password": "неверный"})).status_code
            for _ in range(6)
        ]
        assert codes == [401] * 5 + [429]


async def test_success_resets_failures(client):
    for _ in range(4):
        await client.post("/api/auth/login", json={"login": "vera", "password": "неверный"})
    assert await login(client, "vera")
    for _ in range(4):
        assert (await client.post("/api/auth/login", json={"login": "vera", "password": "неверный"})).status_code == 401


async def test_parallel_guessing_is_stopped(client):
    """Из любого числа одновременных попыток пароль проверяется не больше пяти раз (приёмка версии 2)."""
    responses = await asyncio.gather(
        *[client.post("/api/auth/login", json={"login": "gleb", "password": f"неверный-{n}"}) for n in range(30)]
    )
    codes = [r.status_code for r in responses]
    assert set(codes) <= {401, 429}
    assert codes.count(401) <= 5, codes
    after = await client.post("/api/auth/login", json={"login": "gleb", "password": TEST_PASSWORD})
    assert after.status_code == 429


async def test_guessing_current_password_through_an_open_tab_is_limited(client):
    """Смена пароля в чужой открытой вкладке — не обход ограничения: счётчик общий со входом."""
    dina = await login(client, "dina")
    for _ in range(5):
        wrong = await client.post(
            "/api/auth/password", json={"current_password": "неверный", "new_password": GOOD_PASSWORD}, headers=auth(dina)
        )
        assert wrong.status_code == 403
    sixth = await client.post(
        "/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": GOOD_PASSWORD}, headers=auth(dina)
    )
    assert sixth.status_code == 429
    assert (await client.post("/api/auth/login", json={"login": "dina", "password": TEST_PASSWORD})).status_code == 429


async def test_two_admins_disabling_each_other_at_once(client, user_ids):
    """Действия администраторов идут по очереди: ни ошибки 500, ни сервиса без администратора."""
    admin = await login(client, "admin")
    second = await _invite(client, admin, "kira", role="admin")
    kira = (await _setup(client, second["setup"]["token"])).json()["token"]
    for _ in range(3):
        first, other = await asyncio.gather(
            client.post(f"/api/admin/users/{second['user']['id']}/disable", headers=auth(admin)),
            client.post(f"/api/admin/users/{user_ids['admin']}/disable", headers=auth(kira)),
        )
        codes = sorted([first.status_code, other.status_code])
        # Первый отключает второго; второй к своей очереди уже не администратор с доступом
        # (403 — если вход ещё действовал при проверке токена, 401 — если уже нет).
        assert codes in ([200, 401], [200, 403]), codes
        survivor, victim = (admin, second["user"]["id"]) if first.status_code == 200 else (kira, user_ids["admin"])
        staff = (await client.get("/api/admin/users", headers=auth(survivor))).json()
        assert sum(1 for u in staff if u["role"] == "admin" and u["status"] != "disabled") == 1
        # Вернуть исходное состояние для следующего круга.
        await client.post(f"/api/admin/users/{victim}/enable", headers=auth(survivor))
        admin = await login(client, "admin")
        kira = await login(client, "kira", GOOD_PASSWORD)


async def test_websocket_opened_while_being_disabled_is_closed(client, app, user_ids, ws_url, monkeypatch):
    """Отключение в промежутке между проверкой сессии и регистрацией соединения (приёмка версии 2)."""
    import json

    from sqlalchemy import update
    from websockets.asyncio.client import connect

    from app.api import realtime as realtime_api

    original = realtime_api.find_session
    calls = 0

    async def find_then_disable(db, token, now):
        nonlocal calls
        calls += 1
        found = await original(db, token, now)
        if calls == 1:  # первая проверка прошла — и сразу после неё доступ отключают
            async with app.state.sessionmaker() as other:
                await other.execute(update(User).where(User.id == user_ids["vera"]).values(is_active=False))
                await other.commit()
        return found

    monkeypatch.setattr(realtime_api, "find_session", find_then_disable)
    vera = await login(client, "vera")
    async with connect(ws_url) as ws:
        await ws.send(json.dumps({"type": "auth", "token": vera}))
        await asyncio.wait_for(ws.wait_closed(), timeout=2)
        assert ws.close_code == 4401
    assert calls == 2  # сессия перепроверена после регистрации соединения


# --- смена и сброс пароля --------------------------------------------------------------


async def test_password_change_keeps_this_tab_and_signs_out_others(client, open_tab):
    here = await login(client, "dina")
    elsewhere = await login(client, "dina")
    other_tab = await open_tab(elsewhere)

    wrong = await client.post(
        "/api/auth/password", json={"current_password": "неверный", "new_password": GOOD_PASSWORD}, headers=auth(here)
    )
    assert wrong.status_code == 403
    weak = await client.post(
        "/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "короткий"}, headers=auth(here)
    )
    assert weak.status_code == 422

    done = await client.post(
        "/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": GOOD_PASSWORD}, headers=auth(here)
    )
    assert done.status_code == 204
    assert (await client.get("/api/auth/me", headers=auth(here))).status_code == 200
    assert (await client.get("/api/auth/me", headers=auth(elsewhere))).status_code == 401
    assert await other_tab.close_code() == 4401
    assert (await client.post("/api/auth/login", json={"login": "dina", "password": TEST_PASSWORD})).status_code == 401
    assert await login(client, "dina", GOOD_PASSWORD)


async def test_reset_link_invalidates_old_password_and_sessions(client, user_ids):
    admin = await login(client, "admin")
    vera = await login(client, "vera")
    reset = await client.post(f"/api/admin/users/{user_ids['vera']}/setup-link", headers=auth(admin))
    assert reset.status_code == 200
    assert reset.json()["user"]["status"] == "invited"

    assert (await client.get("/api/auth/me", headers=auth(vera))).status_code == 401
    assert (await client.post("/api/auth/login", json={"login": "vera", "password": TEST_PASSWORD})).status_code == 401
    assert (await _setup(client, reset.json()["setup"]["token"])).status_code == 200


# --- журнал действий -------------------------------------------------------------------


async def test_audit_log_records_who_did_what(client, user_ids):
    admin = await login(client, "admin")
    created = await _invite(client, admin)
    await _setup(client, created["setup"]["token"])
    await client.post(f"/api/admin/users/{created['user']['id']}/disable", headers=auth(admin))

    events = (await client.get("/api/admin/audit", headers=auth(admin))).json()
    assert [(e["action"], e["actor"], e["target"]) for e in events] == [
        ("user_disabled", "Администратор", "Пётр Сидоров"),
        ("password_set", "Пётр Сидоров", "Пётр Сидоров"),
        ("user_invited", "Администратор", "Пётр Сидоров"),
    ]
    older = (await client.get("/api/admin/audit", params={"before_id": events[0]["id"], "limit": 1}, headers=auth(admin))).json()
    assert [e["action"] for e in older] == ["password_set"]
