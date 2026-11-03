"""WebSocket: вход, сигналы и их получатели, сроки, выход, параллельные изменения (D-039 … D-041).

Каждая «вкладка» — отдельное настоящее соединение WebSocket к серверу uvicorn.
Отсутствие сигнала проверяется через ping: сигналы ставятся в очередь соединения
до ответа HTTP, поэтому если следующим пришёл pong — сигнала не было.
"""

import asyncio
import json
from datetime import timedelta

import pytest
from websockets.asyncio.client import connect

from app.realtime import CLOSE_TRY_AGAIN, Connection, DeadlineTicker
from tests.helpers import (
    SUBMISSION_END,
    VOTING_END,
    auth,
    create_contest,
    login,
    revoke,
    snapshot,
    submit_idea,
    vote,
)

pytestmark = pytest.mark.usefixtures("demo_users")

PARTICIPANTS = ("anna", "boris", "vera")
SIGNAL_KEYS = {"type", "contest_id", "revision"}


@pytest.fixture
async def raw_ws(ws_url):
    opened: list = []

    async def _connect():
        ws = await connect(ws_url)
        opened.append(ws)
        return ws

    yield _connect
    for ws in opened:
        await ws.close()


@pytest.fixture
async def world(client, user_ids):
    tokens = {u: await login(client, u) for u in ("organizer", *PARTICIPANTS, "dina")}
    contest = await create_contest(
        client, tokens["organizer"], participants=[user_ids[u] for u in PARTICIPANTS]
    )
    return {"t": tokens, "cid": contest["id"]}


async def current_revision(client, token, contest_id) -> int:
    return (await snapshot(client, token, contest_id)).json()["revision"]


def assert_signal(message: dict, kind: str, contest_id: int, revision: int) -> None:
    # Сигнал — только «что-то изменилось», без данных конкурса (D-014).
    assert set(message) == SIGNAL_KEYS
    assert message == {"type": kind, "contest_id": contest_id, "revision": revision}


# --- вход -------------------------------------------------------------------


async def test_ready_message_identifies_user_by_session(client, open_tab, user_ids):
    tab = await open_tab(await login(client, "anna"))
    assert tab.ready["user_id"] == user_ids["anna"]
    assert set(tab.ready) == {"type", "user_id", "server_time"}


async def test_no_auth_message_closes_with_4408(raw_ws):
    ws = await raw_ws()
    await asyncio.wait_for(ws.wait_closed(), 2.0)
    assert ws.close_code == 4408


@pytest.mark.parametrize(
    "first_message",
    ["не json", "[]", '{"type": "subscribe"}', '{"type": "auth"}', '{"type": "auth", "token": 5}'],
)
async def test_malformed_auth_message_closes_with_4400(raw_ws, first_message):
    ws = await raw_ws()
    await ws.send(first_message)
    await asyncio.wait_for(ws.wait_closed(), 2.0)
    assert ws.close_code == 4400


async def test_invalid_or_expired_token_closes_with_4401(client, raw_ws, clock):
    ws = await raw_ws()
    await ws.send(json.dumps({"type": "auth", "token": "not-a-real-token"}))
    await asyncio.wait_for(ws.wait_closed(), 2.0)
    assert ws.close_code == 4401

    token = await login(client, "anna")
    clock.advance(timedelta(hours=24))  # ровно в expires_at сессия уже недействительна
    ws = await raw_ws()
    await ws.send(json.dumps({"type": "auth", "token": token}))
    await asyncio.wait_for(ws.wait_closed(), 2.0)
    assert ws.close_code == 4401


async def test_ping_pong_and_unknown_messages_are_ignored(client, open_tab):
    tab = await open_tab(await login(client, "anna"))
    await tab.ws.send(json.dumps({"type": "что-то другое", "user_id": 1, "role": "organizer"}))
    await tab.expect_nothing()


# --- получатели сигналов ---------------------------------------------------


async def test_submission_signals_only_organizer_and_author(client, world, open_tab):
    t, cid = world["t"], world["cid"]
    org = await open_tab(t["organizer"])
    anna_1, anna_2 = await open_tab(t["anna"]), await open_tab(await login(client, "anna"))
    boris, dina = await open_tab(t["boris"]), await open_tab(t["dina"])

    response = await submit_idea(client, t["anna"], cid, "Велопарковка")
    assert response.status_code == 201
    revision = await current_revision(client, t["organizer"], cid)

    for tab in (org, anna_1, anna_2):
        assert_signal(await tab.next(), "contest_changed", cid, revision)
    # Чужие идеи во время подачи не видны — и сигнала о них нет (D-039, REVIEW Б2).
    await boris.expect_nothing()
    await dina.expect_nothing()


async def test_edit_signals_only_organizer_and_author(client, world, open_tab):
    t, cid = world["t"], world["cid"]
    idea = (await submit_idea(client, t["anna"], cid)).json()
    org, anna, boris = await open_tab(t["organizer"]), await open_tab(t["anna"]), await open_tab(t["boris"])

    response = await client.put(
        f"/api/ideas/{idea['id']}",
        json={"title": "Новое", "description": "Текст", "version": idea["version"]},
        headers=auth(t["anna"]),
    )
    assert response.status_code == 200

    revision = await current_revision(client, t["organizer"], cid)
    assert_signal(await org.next(), "contest_changed", cid, revision)
    assert_signal(await anna.next(), "contest_changed", cid, revision)
    await boris.expect_nothing()


async def test_vote_signals_only_organizer_and_voter(client, world, open_tab, clock):
    t, cid = world["t"], world["cid"]
    idea = (await submit_idea(client, t["anna"], cid)).json()["id"]
    clock.set(SUBMISSION_END)
    org, boris = await open_tab(t["organizer"]), await open_tab(t["boris"])
    anna, vera, dina = await open_tab(t["anna"]), await open_tab(t["vera"]), await open_tab(t["dina"])

    assert (await vote(client, t["boris"], idea)).status_code == 201
    revision = await current_revision(client, t["organizer"], cid)
    assert_signal(await org.next(), "contest_changed", cid, revision)
    assert_signal(await boris.next(), "contest_changed", cid, revision)
    # Счёт участникам не виден: ни автору идеи, ни другим участникам сигнал не нужен.
    for tab in (anna, vera, dina):
        await tab.expect_nothing()

    assert (await revoke(client, t["boris"], idea)).status_code == 204
    assert_signal(await org.next(), "contest_changed", cid, revision + 1)
    assert_signal(await boris.next(), "contest_changed", cid, revision + 1)
    await anna.expect_nothing()


async def test_delete_during_voting_signals_everyone_in_contest(client, world, open_tab, clock):
    """Идея, удалённая во время голосования, исчезает у всех сразу (F19)."""
    t, cid = world["t"], world["cid"]
    idea = (await submit_idea(client, t["anna"], cid)).json()["id"]
    clock.set(SUBMISSION_END)
    tabs = {u: await open_tab(t[u]) for u in ("organizer", *PARTICIPANTS)}
    dina = await open_tab(t["dina"])

    assert (await client.delete(f"/api/ideas/{idea}", headers=auth(t["anna"]))).status_code == 204

    revision = await current_revision(client, t["organizer"], cid)
    for who, tab in tabs.items():
        assert_signal(await tab.next(), "contest_changed", cid, revision)
        # После сигнала снимок уже без идеи.
        assert (await snapshot(client, t[who], cid)).json()["ideas"] == []
    await dina.expect_nothing()


async def test_delete_during_submission_signals_only_organizer_and_author(client, world, open_tab):
    t, cid = world["t"], world["cid"]
    idea = (await submit_idea(client, t["anna"], cid)).json()["id"]
    org, anna, boris = await open_tab(t["organizer"]), await open_tab(t["anna"]), await open_tab(t["boris"])

    assert (await client.delete(f"/api/ideas/{idea}", headers=auth(t["anna"]))).status_code == 204

    revision = await current_revision(client, t["organizer"], cid)
    assert_signal(await org.next(), "contest_changed", cid, revision)
    assert_signal(await anna.next(), "contest_changed", cid, revision)
    await boris.expect_nothing()


async def test_new_contest_signals_its_participants_and_organizers(client, open_tab, user_ids):
    org_token = await login(client, "organizer")
    org_1, org_2 = await open_tab(org_token), await open_tab(await login(client, "organizer"))
    anna, dina = await open_tab(await login(client, "anna")), await open_tab(await login(client, "dina"))

    await create_contest(client, org_token, participants=[user_ids["anna"]])

    for tab in (org_1, org_2, anna):
        assert await tab.next() == {"type": "contests_changed"}
    await dina.expect_nothing()


async def test_rejected_and_repeated_requests_send_no_signal(client, world, open_tab, clock):
    t, cid = world["t"], world["cid"]
    idea = (await submit_idea(client, t["anna"], cid)).json()
    clock.set(SUBMISSION_END)
    assert (await vote(client, t["boris"], idea["id"])).status_code == 201
    org = await open_tab(t["organizer"])

    assert (await vote(client, t["boris"], idea["id"])).status_code == 200  # повтор
    assert (await revoke(client, t["vera"], idea["id"])).status_code == 204  # голоса не было
    assert (await vote(client, t["anna"], idea["id"])).status_code == 403  # своя идея
    assert (await submit_idea(client, t["anna"], cid)).status_code == 409  # подача закрыта
    response = await client.put(
        f"/api/ideas/{idea['id']}",
        json={"title": "x", "description": "y", "version": idea["version"]},
        headers=auth(t["anna"]),
    )
    assert response.status_code == 409
    await org.expect_nothing()


async def test_signals_carry_no_contest_data_for_any_role(client, world, open_tab, clock):
    """Ни в одном сигнале нет названий, авторов, счёта — только тип, номер и revision."""
    t, cid = world["t"], world["cid"]
    tabs = {u: await open_tab(t[u]) for u in ("organizer", *PARTICIPANTS)}
    idea = (await submit_idea(client, t["anna"], cid, "Секретное название", "Секретный текст")).json()
    clock.set(SUBMISSION_END)
    await vote(client, t["boris"], idea["id"])
    await client.delete(f"/api/ideas/{idea['id']}", headers=auth(t["anna"]))

    for who, tab in tabs.items():
        await tab.ws.send(json.dumps({"type": "ping"}))
        while (message := await tab.next()) != {"type": "pong"}:
            assert set(message) == SIGNAL_KEYS, who
            text = json.dumps(message, ensure_ascii=False)
            assert "Секрет" not in text and "Анна" not in text, who


# --- сроки ------------------------------------------------------------------


async def test_deadline_tick_signals_phase_change_once(client, world, open_tab, app, clock):
    t, cid = world["t"], world["cid"]
    tabs = [await open_tab(t[u]) for u in ("organizer", *PARTICIPANTS)]
    dina = await open_tab(t["dina"])
    revision = await current_revision(client, t["organizer"], cid)
    ticker = app.state.deadlines

    # Срок подачи ещё не наступил — сигнала нет.
    assert await ticker.tick(clock.now(), SUBMISSION_END - timedelta(microseconds=1)) == []
    # Ровно в момент срока раунд закрыт (D-007).
    assert await ticker.tick(SUBMISSION_END - timedelta(microseconds=1), SUBMISSION_END) == [cid]
    for tab in tabs:
        assert_signal(await tab.next(), "phase_changed", cid, revision)
    await dina.expect_nothing()

    # Следующий промежуток не содержит того же срока — повторного сигнала нет.
    assert await ticker.tick(SUBMISSION_END, SUBMISSION_END + timedelta(minutes=1)) == []
    assert await ticker.tick(SUBMISSION_END + timedelta(minutes=1), VOTING_END) == [cid]
    for tab in tabs:
        assert_signal(await tab.next(), "phase_changed", cid, revision)


async def test_background_ticker_announces_deadline_when_clock_passes_it(
    client, world, open_tab, app, clock
):
    t, cid = world["t"], world["cid"]
    org = await open_tab(t["organizer"])
    app.state.deadlines.start()
    try:
        await org.expect_nothing()
        clock.set(SUBMISSION_END)  # задача проверяет сроки не реже deadline_max_sleep_seconds
        message = await org.next()
        assert message["type"] == "phase_changed" and message["contest_id"] == cid
        # Снимок после сигнала — уже голосование.
        assert (await snapshot(client, t["organizer"], cid)).json()["contest"]["phase"] == "voting"
    finally:
        await app.state.deadlines.stop()


async def test_background_ticker_wakes_up_for_new_contest(client, open_tab, app, clock, user_ids):
    """Задача спит до 60 с; создание конкурса будит её, и она ждёт уже до его срока."""
    ticker = DeadlineTicker(app.state.sessionmaker, clock, app.state.hub, max_sleep_seconds=60)
    org_token = await login(client, "organizer")
    ticker.start()
    try:
        await asyncio.sleep(0.05)  # задача проверила сроки (конкурсов нет) и уснула на 60 с
        contest = await create_contest(
            client,
            org_token,
            participants=[user_ids["anna"]],
            submission_deadline=clock.now() + timedelta(milliseconds=300),
        )
        org = await open_tab(org_token)
        clock.advance(timedelta(milliseconds=300))
        message = await org.next(timeout=3)
        assert message == {"type": "phase_changed", "contest_id": contest["id"], "revision": 1}
    finally:
        await ticker.stop()


# --- выход, срок сессии, переподключение ------------------------------------


async def test_logout_closes_only_this_tabs_connection(client, open_tab):
    token_1, token_2 = await login(client, "anna"), await login(client, "anna")
    tab_1, tab_2 = await open_tab(token_1), await open_tab(token_2)

    assert (await client.post("/api/auth/logout", headers=auth(token_1))).status_code == 204

    assert await tab_1.close_code() == 4401
    await tab_2.expect_nothing()  # вторая вкладка того же пользователя работает


async def test_expired_session_connection_is_closed_on_next_signal(client, open_tab, clock, user_ids):
    anna_token = await login(client, "anna")
    anna = await open_tab(anna_token)
    clock.advance(timedelta(hours=24))
    org_token = await login(client, "organizer")

    await create_contest(
        client,
        org_token,
        participants=[user_ids["anna"]],
        submission_deadline=clock.now() + timedelta(hours=1),
        voting_deadline=clock.now() + timedelta(hours=2),
    )

    assert await anna.close_code() == 4401


async def test_reconnect_then_snapshot_shows_changes_made_while_offline(client, world, open_tab):
    t, cid = world["t"], world["cid"]
    org = await open_tab(t["organizer"])
    await org.ws.close()

    await submit_idea(client, t["anna"], cid)
    await submit_idea(client, t["boris"], cid)

    again = await open_tab(t["organizer"])
    snap = (await snapshot(client, t["organizer"], cid)).json()
    assert snap["stats"]["ideas_count"] == 2
    await again.expect_nothing()  # сигналы за время отключения не копятся — нужен снимок


# --- параллельные изменения -------------------------------------------------


async def test_parallel_votes_each_signal_unique_revision_and_last_matches_snapshot(
    client, world, open_tab, clock
):
    t, cid = world["t"], world["cid"]
    ideas = [(await submit_idea(client, t[u], cid, f"Идея {u}")).json()["id"] for u in PARTICIPANTS]
    clock.set(SUBMISSION_END)
    org = await open_tab(t["organizer"])
    start = await current_revision(client, t["organizer"], cid)

    voters = [await login(client, u) for u in PARTICIPANTS for _ in range(2)]  # по 2 вкладки
    requests = [
        vote(client, token, idea)
        for token in voters
        for idea in ideas
    ]
    responses = await asyncio.gather(*requests)
    created = sum(r.status_code == 201 for r in responses)
    assert created == 6  # 3 человека × 2 чужие идеи; повторы из вторых вкладок — 200

    revisions = [(await org.next())["revision"] for _ in range(created)]
    # Каждое изменение — свой номер; порядок прихода может отличаться (D-039).
    assert sorted(revisions) == list(range(start + 1, start + created + 1))
    assert max(revisions) == await current_revision(client, t["organizer"], cid)
    await org.expect_nothing()


# --- очередь медленного клиента ---------------------------------------------


class _SlowWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed_with: int | None = None

    async def send_json(self, message: dict) -> None:
        self.sent.append(message)

    async def close(self, code: int) -> None:
        self.closed_with = code


async def test_overflowing_queue_closes_connection_instead_of_growing(clock):
    websocket = _SlowWebSocket()
    connection = Connection(
        websocket,
        user_id=1,
        role="employee",
        session_id=1,
        expires_at=clock.now() + timedelta(hours=1),
        queue_limit=2,
    )
    for n in range(5):  # клиент не читает: сигналы копятся
        connection.send({"n": n})
    assert connection.closing

    await connection.run()
    assert websocket.sent == [{"n": 0}, {"n": 1}]
    assert websocket.closed_with == CLOSE_TRY_AGAIN
