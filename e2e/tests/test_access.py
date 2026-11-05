"""Права доступа и сроки проверяет сервер, а не только интерфейс (D-005, D-050).

Каждый тест делает то, что интерфейс не предлагает (прямая ссылка, прямой запрос с токеном
вкладки, устаревшая страница), и проверяет фактическое состояние через API.
"""

import re
import uuid
from datetime import datetime, timedelta

from playwright.sync_api import Page, expect

from helpers import Link, card, parse_time, phase_badge, tab_token, unique, wait_until


def test_non_participant_cannot_see_or_act(people, api):
    org_api = api("organizer")
    contest = org_api.create_contest(unique("Только для Анны"), submission_in=600, voting_in=600, participants=["anna"])
    idea = api("anna").submit(contest["id"], "Идея Анны")

    dina = people("dina").tab()
    expect(dina.get_by_role("link", name=re.compile(re.escape(contest["topic"])))).to_have_count(0)
    dina.goto(f"/contests/{contest['id']}")
    expect(dina.get_by_role("heading", name="Конкурс не найден")).to_be_visible()

    # Прямые запросы с токеном её вкладки — тоже «не найдено»: чужой конкурс не раскрывается.
    token = {"Authorization": f"Bearer {tab_token(dina)}"}
    request = dina.request
    assert request.get(f"/api/contests/{contest['id']}", headers=token).status == 404
    submit = request.post(
        f"/api/contests/{contest['id']}/ideas",
        headers=token,
        data={"title": "Чужая", "description": "Нельзя", "client_request_id": str(uuid.uuid4())},
    )
    assert submit.status == 404
    assert request.post(f"/api/ideas/{idea['id']}/vote", headers=token).status == 404
    assert org_api.snapshot(contest["id"])["stats"]["ideas_count"] == 1


def test_participant_cannot_use_organizer_functions(people, api):
    anna = people("anna").tab()
    expect(anna.get_by_role("link", name="Новый конкурс", exact=True)).to_have_count(0)
    anna.goto("/contests/new")
    expect(anna).to_have_url(re.compile(r"/contests$"))  # страница организатора недоступна

    before = len(api("organizer").contests())
    token = {"Authorization": f"Bearer {tab_token(anna)}"}
    now = datetime.now().astimezone()
    created = anna.request.post(
        "/api/contests",
        headers=token,
        data={
            "topic": "Самовольный конкурс",
            "submission_deadline": (now + timedelta(hours=1)).isoformat(),
            "voting_deadline": (now + timedelta(hours=2)).isoformat(),
            "client_request_id": str(uuid.uuid4()),
        },
    )
    assert created.status == 403
    assert len(api("organizer").contests()) == before
    any_contest = api("anna").contests()[0]["id"]
    assert anna.request.get(f"/api/contests/{any_contest}/participants", headers=token).status == 403
    assert anna.request.get("/api/users", headers=token).status == 403


def test_organizer_cannot_submit_or_vote(people, api):
    org_api = api("organizer")
    contest = org_api.create_contest(unique("Без организатора"), submission_in=600, voting_in=600)
    org = people("organizer").tab(f"/contests/{contest['id']}")
    expect(org.get_by_role("heading", name="Идеи скрыты до начала голосования")).to_be_visible()
    expect(org.locator("#new-idea-title")).to_have_count(0)

    submit = org_api.post(
        f"/api/contests/{contest['id']}/ideas",
        {"title": "От организатора", "description": "Нельзя", "client_request_id": str(uuid.uuid4())},
    )
    assert submit.status == 403
    idea = api("anna").submit(contest["id"], "Идея Анны")
    assert org_api.vote(idea["id"]).status == 403
    assert org_api.snapshot(contest["id"])["stats"]["ideas_count"] == 1


def _freeze_page_time(page: Page) -> None:
    page.clock.install()


def test_stale_page_cannot_vote_after_deadline(people, api):
    """Страница «застряла» в голосовании (фоновая вкладка, сон компьютера): часы страницы
    стоят, сигналы о смене фазы не доходят. После срока кнопка «Голосовать» ещё видна,
    но голос сервер не примет."""
    org_api = api("organizer")
    contest = org_api.create_contest(unique("Устаревшая страница"), submission_in=6, voting_in=14)
    idea = api("anna").submit(contest["id"], "Идея Анны")
    wait_until(parse_time(contest["submission_deadline"]), org_api)

    links: list[Link] = []
    boris = people("boris").tab(
        f"/contests/{contest['id']}",
        before=lambda page: (_freeze_page_time(page), links.append(Link(page))),
    )
    expect(phase_badge(boris)).to_contain_text("Голосование")
    links[0].hold_signals()  # сигнал phase_changed до страницы не дойдёт
    boris.clock.pause_at(datetime.now().astimezone() + timedelta(seconds=1))  # таймер срока не сработает

    wait_until(parse_time(contest["voting_deadline"]), org_api, extra=1.0)
    vote = card(boris, "Идея Анны").get_by_role("button", name="Голосовать")
    expect(vote).to_be_visible()  # страница всё ещё думает, что идёт голосование
    vote.click()

    expect(boris.get_by_text("Голосование закрыто")).to_be_visible()  # отказ сервера показан
    expect(phase_badge(boris)).to_contain_text("Завершён")  # и страница перечитала состояние
    snap = api("boris").snapshot(contest["id"])
    assert snap["contest"]["phase"] == "finished"
    assert [i["votes_count"] for i in snap["ideas"] if i["id"] == idea["id"]] == [0]


def test_logout_in_one_tab_keeps_the_other(people, api):
    anna = people("anna")
    first, second = anna.tab(), anna.tab()
    first_token = tab_token(first)

    first.get_by_role("button", name="Выйти").click()
    expect(first).to_have_url(re.compile(r"/login"))
    # Вторая вкладка работает со своим входом.
    second.get_by_role("link", name="Входящие").click()
    expect(second.get_by_role("heading", name="Входящие")).to_be_visible()
    expect(second.get_by_text("Онлайн")).to_be_visible()
    assert second.request.get("/api/auth/me", headers={"Authorization": f"Bearer {tab_token(second)}"}).ok
    # Токен первой вкладки отозван на сервере.
    assert first.request.get("/api/auth/me", headers={"Authorization": f"Bearer {first_token}"}).status == 401


def test_new_tab_needs_its_own_login(people):
    anna = people("anna")
    anna.tab()
    fresh = anna.context.new_page()  # тот же браузер, новая вкладка
    fresh.goto("/contests")
    expect(fresh).to_have_url(re.compile(r"/login"))
    fresh.close()


def test_pages_are_served_with_security_headers(api):
    """CSP и другие заголовки (D-059): страница и её файлы — только со своего адреса."""
    response = api("anna").request.get("/contests")
    headers = response.headers
    csp = headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
