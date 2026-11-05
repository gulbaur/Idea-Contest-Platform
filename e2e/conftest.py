"""Фикстуры E2E (D-055).

- `api(login)` — REST API от имени пользователя (проверка фактического состояния);
- `people(login)` — человек со своим браузерным профилем; `person.tab()` открывает новую
  вкладку и входит в ней (у каждой вкладки свой вход, D-003);
- при падении теста в `results/` сохраняются снимки всех вкладок и трассы Playwright;
- необработанная ошибка JavaScript на любой странице — провал теста.
"""

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

from helpers import BASE_URL, NAMES, Api

RESULTS = Path(__file__).parent / "results"

# Сигналы и переподключения занимают доли секунды, но машина проверки может быть медленной.
expect.set_options(timeout=10_000)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    setattr(item, f"rep_{report.when}", report)
    return report


@pytest.fixture(scope="session")
def playwright_session():
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture(scope="session")
def browser(playwright_session) -> Browser:
    browser = playwright_session.chromium.launch()
    yield browser
    browser.close()


@pytest.fixture(scope="session")
def api(playwright_session) -> Callable[[str], Api]:
    request = playwright_session.request.new_context(base_url=BASE_URL)
    sessions: dict[str, Api] = {}

    def get(login: str) -> Api:
        if login not in sessions:
            sessions[login] = Api(request, login)
        return sessions[login]

    yield get
    request.dispose()


class Person:
    """Человек за своим компьютером: отдельный профиль браузера, сколько угодно вкладок."""

    def __init__(self, browser: Browser, login: str, errors: list[str]) -> None:
        self.login = login
        self.name = NAMES[login]
        self.errors = errors
        self.context = browser.new_context(
            base_url=BASE_URL,
            viewport={"width": 1366, "height": 900},
            locale="ru-RU",
            timezone_id="Asia/Almaty",
        )
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.tabs: list[Page] = []

    def tab(self, path: str | None = None, *, before: Callable[[Page], None] | None = None) -> Page:
        """Новая вкладка с входом через кнопку демо-аккаунта; затем — переход на `path`.

        `before(page)` вызывается до загрузки приложения — например, чтобы перехватить
        WebSocket или подменить часы страницы.
        """
        page = self.context.new_page()
        number = len(self.tabs) + 1
        page.on("pageerror", lambda error: self.errors.append(f"{self.login}, вкладка {number}: {error}"))
        # Нарушение политики безопасности (CSP, D-059) браузер пишет в консоль — это тоже ошибка.
        page.on(
            "console",
            lambda message: "Content Security Policy" in message.text
            and self.errors.append(f"{self.login}, вкладка {number}: {message.text}"),
        )
        if before is not None:
            before(page)
        page.goto("/login")
        page.get_by_role("button", name=re.compile(self.name)).click()
        expect(page.get_by_role("heading", name="Конкурсы", exact=True)).to_be_visible()
        expect(page.get_by_text("Онлайн")).to_be_visible()
        if path is not None:
            page.goto(path)
        self.tabs.append(page)
        return page

    def finish(self, failed: bool, folder: Path) -> None:
        if failed:
            folder.mkdir(parents=True, exist_ok=True)
            for number, page in enumerate(self.tabs, start=1):
                try:
                    page.screenshot(path=folder / f"{self.login}-{number}.png", full_page=True)
                except Exception:  # noqa: BLE001 — страница могла уже закрыться
                    pass
            self.context.tracing.stop(path=folder / f"{self.login}-trace.zip")
        else:
            self.context.tracing.stop()
        self.context.close()


@pytest.fixture
def people(browser, request) -> Callable[[str], Person]:
    created: dict[str, Person] = {}
    errors: list[str] = []

    def person(login: str) -> Person:
        if login not in created:
            created[login] = Person(browser, login, errors)
        return created[login]

    yield person

    report = getattr(request.node, "rep_call", None)
    folder = RESULTS / re.sub(r"[^\w.-]+", "_", request.node.nodeid)
    for someone in created.values():
        someone.finish(bool(report and report.failed), folder)
    assert not errors, "ошибки JavaScript на страницах:\n" + "\n".join(errors)
