"""Помощники E2E (D-055).

- `Api` — REST API от имени пользователя, отдельная сессия: так тест проверяет фактическое
  состояние системы, а не только надписи в браузере;
- `Barrier` — задерживает запросы нескольких вкладок и отпускает их разом: одновременные
  действия воспроизводятся каждый раз;
- `Link` — управляемая связь страницы с сервером по WebSocket: обрыв, отказ в
  переподключении, «молчащее» соединение, задержка сигналов;
- действия в интерфейсе, которые повторяются в разных тестах.
"""

import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta

from playwright.sync_api import APIRequestContext, Page, Route, WebSocketRoute, expect

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo-password")

NAMES = {
    "organizer": "Организатор",
    "anna": "Анна Смирнова",
    "boris": "Борис Котов",
    "vera": "Вера Орлова",
    "gleb": "Глеб Лебедев",
    "dina": "Дина Ахметова",
}
EMPLOYEE_NAMES = [name for login, name in NAMES.items() if login != "organizer"]

# Демо-конкурсы (backend/app/demo.py, D-054).
DEMO_SUBMISSION = "Как сделать офис уютнее"
DEMO_VOTING = "Как сократить время на совещания"
DEMO_FINISHED = "Как сделать обеды в офисе удобнее"


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Api:
    """REST API от имени одного пользователя — независимая от браузера сессия."""

    def __init__(self, request: APIRequestContext, login: str) -> None:
        self.request = request
        self.login = login
        response = request.post("/api/auth/login", data={"login": login, "password": DEMO_PASSWORD})
        assert response.ok, response.text()
        body = response.json()
        self.token = body["token"]
        self.user = body["user"]

    @property
    def id(self) -> int:
        return self.user["id"]

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, path: str):
        return self.request.get(path, headers=self._headers())

    def post(self, path: str, data: dict | None = None):
        return self.request.post(path, headers=self._headers(), data=data)

    def delete(self, path: str):
        return self.request.delete(path, headers=self._headers())

    # --- чтение ---------------------------------------------------------------

    def server_time(self) -> datetime:
        return parse_time(self.request.get("/api/health").json()["server_time"])

    def contests(self) -> list[dict]:
        response = self.get("/api/contests")
        assert response.ok, response.text()
        return response.json()

    def contest_by_topic(self, topic: str) -> dict:
        matches = [c for c in self.contests() if c["topic"] == topic]
        assert matches, f"нет конкурса «{topic}»"
        return matches[0]

    def snapshot(self, contest_id: int) -> dict:
        response = self.get(f"/api/contests/{contest_id}")
        assert response.status == 200, response.text()
        return response.json()

    def idea(self, contest_id: int, title: str) -> dict | None:
        return next((i for i in self.snapshot(contest_id)["ideas"] if i["title"] == title), None)

    def emails(self, contest_id: int | None = None) -> list[dict]:
        path = "/api/emails" + (f"?contest_id={contest_id}" if contest_id else "")
        response = self.get(path)
        assert response.ok, response.text()
        return response.json()

    def user_ids(self) -> dict[str, int]:
        """Только организатору: логин → id сотрудника."""
        return {u["login"]: u["id"] for u in self.get("/api/users").json()}

    # --- действия ---------------------------------------------------------------

    def create_contest(
        self,
        topic: str,
        *,
        submission_in: float,
        voting_in: float,
        participants: list[str] | None = None,
    ) -> dict:
        """Конкурс со сроками через `submission_in` и `submission_in + voting_in` секунд
        по часам сервера."""
        now = self.server_time()
        payload = {
            "topic": topic,
            "submission_deadline": (now + timedelta(seconds=submission_in)).isoformat(),
            "voting_deadline": (now + timedelta(seconds=submission_in + voting_in)).isoformat(),
            "client_request_id": str(uuid.uuid4()),
        }
        if participants is not None:
            ids = self.user_ids()
            payload["participant_ids"] = [ids[login] for login in participants]
        response = self.post("/api/contests", payload)
        assert response.status == 201, response.text()
        return response.json()

    def submit(self, contest_id: int, title: str, description: str = "Описание идеи") -> dict:
        response = self.post(
            f"/api/contests/{contest_id}/ideas",
            {"title": title, "description": description, "client_request_id": str(uuid.uuid4())},
        )
        assert response.status == 201, response.text()
        return response.json()

    def vote(self, idea_id: int):
        return self.post(f"/api/ideas/{idea_id}/vote")

    def revoke(self, idea_id: int):
        return self.delete(f"/api/ideas/{idea_id}/vote")


def unique(topic: str) -> str:
    """Уникальная тема: тесты не мешают друг другу и повторным запускам."""
    return f"{topic} · {uuid.uuid4().hex[:6]}"


def wait_until(moment: datetime, api: Api, extra: float = 0.3) -> None:
    """Подождать, пока на часах сервера наступит `moment` (плюс небольшой запас).

    Ждём по самим часам сервера, а не «N секунд»: системные часы машины могут
    подстраиваться скачком (так бывает в виртуальной машине Docker), и тогда пауза
    по секундомеру закончилась бы раньше срока по часам сервера.
    """
    target = moment + timedelta(seconds=extra)
    while (left := (target - api.server_time()).total_seconds()) > 0:
        time.sleep(min(left, 1.0))


# --- интерфейс ------------------------------------------------------------------


def card(page: Page, title: str):
    """Карточка идеи на странице участника."""
    return page.locator("article[data-idea-id]").filter(
        has=page.get_by_role("heading", name=title, exact=True)
    )


def result_row(page: Page, title: str):
    """Строка результатов (организатор во время голосования, все — в итогах)."""
    return page.locator("li[data-idea-id]").filter(has=page.get_by_role("heading", name=title, exact=True))


def votes_of(page: Page, title: str):
    return result_row(page, title).locator("[data-test=votes]")


def phase_badge(page: Page):
    return page.locator(".phase-badge").first


def submit_idea(page: Page, title: str, description: str = "Описание идеи") -> None:
    page.locator("#new-idea-title").fill(title)
    page.locator("#new-idea-description").fill(description)
    page.get_by_role("button", name="Отправить идею").click()
    expect(card(page, title)).to_be_visible()


def confirm(page: Page, button: str) -> None:
    page.get_by_role("alertdialog").get_by_role("button", name=button).click()


def mark_page(page: Page) -> None:
    """Пометить текущий документ: если страница перезагрузится, пометка пропадёт."""
    page.evaluate("window.__e2eMark = true")


def eventually(check, timeout: float = 15.0, step: float = 0.25):
    """Повторять проверку состояния, пока она не станет истинной (для фоновых заданий)."""
    deadline = time.monotonic() + timeout
    while True:
        result = check()
        if result or time.monotonic() > deadline:
            assert result, "состояние не наступило за отведённое время"
            return result
        time.sleep(step)


def assert_not_reloaded(page: Page) -> None:
    assert page.evaluate("window.__e2eMark === true"), "страница перезагружалась"


def tab_token(page: Page) -> str:
    """Токен входа этой вкладки (sessionStorage, D-003)."""
    return page.evaluate("JSON.parse(sessionStorage.getItem('idea-contest.session')).token")


# --- одновременные запросы ------------------------------------------------------------


class Barrier:
    """Задерживает по одному запросу из каждой страницы и отпускает их разом.

    Пример: две вкладки нажимают «Голосовать» — оба запроса уже ушли из браузера, но до
    сервера дойдут одновременно, только когда тест вызовет `release()`. Так гонка
    воспроизводится каждый раз, а не «если повезёт» (D-055).
    """

    def __init__(self, pages: list[Page], url: str | re.Pattern, methods: tuple[str, ...] = ("POST",)) -> None:
        self.pages = pages
        self.url = url
        self.methods = methods
        self.held: list[Route] = []
        self.released = False
        for page in pages:
            page.route(url, self._hold)

    def _hold(self, route: Route) -> None:
        if self.released or route.request.method not in self.methods:
            route.fallback()
            return
        self.held.append(route)

    def release(self, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        while len(self.held) < len(self.pages):
            assert time.monotonic() < deadline, f"задержано {len(self.held)} из {len(self.pages)} запросов"
            self.pages[0].wait_for_timeout(20)  # даёт Playwright обработать перехваты
        # Сначала отпустить, потом снять перехват: unroute сам отпускает ждущие запросы.
        self.released = True
        for route in self.held:
            route.continue_()
        for page in self.pages:
            page.unroute(self.url, self._hold)


# --- связь по WebSocket -------------------------------------------------------------

SIGNALS = {"contest_changed", "phase_changed", "contests_changed", "schedule_changed", "mail_changed"}


class Link:
    """Связь страницы с сервером по WebSocket под управлением теста (D-055).

    - `cut()` — оборвать соединение и отклонять переподключения, пока не вызван `restore()`;
    - `silence()` — текущее соединение «замолкает»: сокет открыт, но сообщения не доходят
      ни в одну сторону (сон компьютера, смена сети). Новые соединения работают нормально;
    - `hold_signals()` — сигналы об изменениях не доходят до страницы (остальное работает).
    """

    def __init__(self, page: Page) -> None:
        self.connections = 0  # сколько раз страница открывала соединение
        self.refused = 0
        self._down = False
        self._signals_held = False
        self._open: list[tuple[WebSocketRoute, object, dict]] = []
        page.route_web_socket(re.compile(r"/api/ws$"), self._handle)

    def _handle(self, ws: WebSocketRoute) -> None:
        self.connections += 1
        if self._down:
            self.refused += 1
            # Закрыть прямо здесь нельзя: сокет откроется только после выхода из обработчика,
            # и close() ждал бы его вечно. Закрываем на первом сообщении страницы (вход).
            ws.on_message(lambda _message: ws.close(code=1012, reason="e2e: сервер недоступен"))
            return
        server = ws.connect_to_server()
        state = {"silent": False}

        def to_server(message):
            if not state["silent"]:
                server.send(message)

        def to_page(message):
            if state["silent"]:
                return
            if self._signals_held and json.loads(message).get("type") in SIGNALS:
                return
            ws.send(message)

        ws.on_message(to_server)
        server.on_message(to_page)
        self._open.append((ws, server, state))

    def cut(self) -> None:
        self._down = True
        for ws, server, _ in self._open:
            ws.close(code=1012, reason="e2e: обрыв")
            server.close()
        self._open.clear()

    def restore(self) -> None:
        self._down = False

    def silence(self) -> None:
        for _, _, state in self._open:
            state["silent"] = True

    def hold_signals(self) -> None:
        self._signals_held = True

    def release_signals(self) -> None:
        """Снова пропускать сигналы. Задержанные ранее сигналы потеряны — как при сбое сети."""
        self._signals_held = False
