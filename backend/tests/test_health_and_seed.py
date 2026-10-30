"""Проверка работоспособности и демо-данные."""

from sqlalchemy import func, select

from app.models import User
from app.seed import DEMO_USERS, seed_demo_users
from tests.helpers import T0, TEST_PASSWORD


async def test_health_reports_database_and_server_time(client):
    response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    # Время сервера берётся из часов приложения (в тестах — управляемых).
    assert body["server_time"].startswith(T0.strftime("%Y-%m-%dT%H:%M:%S"))


async def test_seed_is_idempotent(app, clock):
    async with app.state.sessionmaker() as db:
        created_first = await seed_demo_users(db, TEST_PASSWORD, clock)
    async with app.state.sessionmaker() as db:
        created_second = await seed_demo_users(db, TEST_PASSWORD, clock)
        total = await db.scalar(select(func.count()).select_from(User))
        roles = dict((await db.execute(select(User.login, User.role))).all())

    assert created_first == len(DEMO_USERS)
    assert created_second == 0
    assert total == len(DEMO_USERS)
    assert roles["organizer"] == "organizer"
    assert sum(1 for role in roles.values() if role == "employee") == len(DEMO_USERS) - 1
