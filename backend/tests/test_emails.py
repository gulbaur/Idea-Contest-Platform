"""Почта порциями: все письма доступны, без пропусков и повторов (D-059)."""

from datetime import timedelta

import pytest
from sqlalchemy import insert

from app.models import Email
from tests.helpers import T0, auth, create_contest, login

pytestmark = pytest.mark.usefixtures("demo_users")


async def _letters(app, contest_id: int, recipient_id: int, count: int, *, same_time: bool = False) -> None:
    """Письма вида final напрямую в БД: одно письмо вида на человека в конкурсе, поэтому count=1."""
    rows = [
        {
            "contest_id": contest_id,
            "recipient_id": recipient_id,
            "to_address": "anna@example.com",
            "kind": "final",
            "subject": f"Письмо {n}",
            "body": "текст",
            "created_at": T0 if same_time else T0 + timedelta(seconds=n),
        }
        for n in range(count)
    ]
    async with app.state.sessionmaker() as db:
        await db.execute(insert(Email), rows)
        await db.commit()


async def _contests(client, organizer: str, count: int) -> list[int]:
    return [(await create_contest(client, organizer, topic=f"Конкурс {n}"))["id"] for n in range(count)]


async def _all_pages(client, token: str, limit: int) -> list[dict]:
    pages, params = [], {"limit": limit}
    while True:
        page = (await client.get("/api/emails", params=params, headers=auth(token))).json()
        pages.extend(page)
        if len(page) < limit:
            return pages
        params = {"limit": limit, "before_time": page[-1]["created_at"], "before_id": page[-1]["id"]}


@pytest.mark.parametrize("same_time", [False, True])
async def test_all_letters_are_reachable_page_by_page(client, app, user_ids, same_time):
    organizer = await login(client, "organizer")
    anna = await login(client, "anna")
    # 250 писем — больше прежнего предела в 200; одно письмо вида final на конкурс.
    for contest_id in await _contests(client, organizer, 250):
        await _letters(app, contest_id, user_ids["anna"], 1, same_time=same_time)

    letters = await _all_pages(client, anna, limit=40)

    assert len(letters) == 250
    assert len({letter["id"] for letter in letters}) == 250  # без повторов
    keys = [(letter["created_at"], letter["id"]) for letter in letters]
    assert keys == sorted(keys, reverse=True)  # от новых к старым


async def test_cursor_does_not_reveal_other_peoples_letters(client, app, user_ids):
    organizer = await login(client, "organizer")
    boris = await login(client, "boris")
    contest_id = (await _contests(client, organizer, 1))[0]
    await _letters(app, contest_id, user_ids["anna"], 1)

    page = await client.get(
        "/api/emails",
        params={"before_time": (T0 + timedelta(days=1)).isoformat(), "before_id": 2_000_000},
        headers=auth(boris),
    )
    assert page.status_code == 200
    assert page.json() == []


async def test_cursor_parts_must_come_together(client):
    anna = await login(client, "anna")
    response = await client.get("/api/emails", params={"before_id": 5}, headers=auth(anna))
    assert response.status_code == 422
