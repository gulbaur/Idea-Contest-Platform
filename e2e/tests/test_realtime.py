"""Обновления в реальном времени и восстановление связи (D-040, D-049, D-055).

Связь страницы с сервером идёт через `Link`: тест обрывает её, отклоняет переподключения,
делает её «молчащей» или теряет сигналы. Изменения во время сбоя делает другой
пользователь через API — после восстановления страница должна показать их сама.
"""

import time

from playwright.sync_api import expect

from helpers import Link, assert_not_reloaded, mark_page, parse_time, phase_badge, unique, wait_until


def open_with_link(people, login: str, path: str):
    links: list[Link] = []
    page = people(login).tab(path, before=lambda p: links.append(Link(p)))
    expect(page.get_by_text("Онлайн")).to_be_visible()
    mark_page(page)
    return page, links[0]


def test_lost_connection_recovers_and_catches_up(people, api):
    contest = api("organizer").create_contest(unique("Обрыв связи"), submission_in=600, voting_in=600)
    org, link = open_with_link(people, "organizer", f"/contests/{contest['id']}")
    count = org.locator("[data-test=ideas-count]")
    expect(count).to_have_text("0")

    link.cut()
    expect(org.get_by_text("Нет связи")).to_be_visible()
    api("anna").submit(contest["id"], "Подана во время обрыва")
    # Пока связи нет, страница переподключается с паузами — сервер «недоступен».
    deadline = time.monotonic() + 15
    while link.refused < 2:
        assert time.monotonic() < deadline, "страница не пытается переподключиться"
        org.wait_for_timeout(200)
    expect(count).to_have_text("0")  # сигнал об изменении потерян вместе со связью

    link.restore()
    expect(org.get_by_text("Онлайн")).to_be_visible(timeout=20_000)
    expect(count).to_have_text("1")  # после переподключения страница перечитала состояние
    api("boris").submit(contest["id"], "Подана после восстановления")
    expect(count).to_have_text("2")  # и снова получает сигналы
    assert_not_reloaded(org)


def test_silent_connection_is_detected_and_replaced(people, api):
    """Сокет открыт, но сообщения не доходят (сон компьютера, смена сети).

    Без пульса страница так и думала бы, что всё в порядке. Клиент шлёт ping раз в 15 с
    и, не получив ответа к следующему, открывает новое соединение (D-049).
    """
    contest = api("organizer").create_contest(unique("Молчащая связь"), submission_in=600, voting_in=600)
    org, link = open_with_link(people, "organizer", f"/contests/{contest['id']}")
    count = org.locator("[data-test=ideas-count]")
    connections = link.connections

    link.silence()
    api("anna").submit(contest["id"], "Подана, пока связь молчит")
    org.wait_for_timeout(1500)
    expect(count).to_have_text("0")  # сигнал не дошёл

    expect(count).to_have_text("1", timeout=45_000)  # новое соединение и перечитанный снимок
    assert link.connections > connections
    expect(org.get_by_text("Онлайн")).to_be_visible()
    assert_not_reloaded(org)


def test_lost_phase_signal_is_covered_by_page_timer(people, api):
    """Сигнал о сроке потерялся — страница всё равно сменит фазу по своему таймеру."""
    org_api = api("organizer")
    contest = org_api.create_contest(unique("Потерянный сигнал"), submission_in=10, voting_in=600)
    anna, link = open_with_link(people, "anna", f"/contests/{contest['id']}")
    expect(phase_badge(anna)).to_contain_text("Приём идей")
    link.hold_signals()

    wait_until(parse_time(contest["submission_deadline"]), org_api)
    expect(phase_badge(anna)).to_contain_text("Голосование", timeout=5_000)
    assert_not_reloaded(anna)


def test_new_contest_appears_in_open_lists(people, api):
    anna = people("anna").tab()
    dina = people("dina").tab()
    mark_page(anna)
    topic = unique("Свежий конкурс в открытом списке")
    api("organizer").create_contest(topic, submission_in=600, voting_in=600, participants=["anna"])

    expect(anna.get_by_role("link", name=topic)).to_be_visible()
    assert_not_reloaded(anna)
    anna.wait_for_timeout(500)
    expect(dina.get_by_role("link", name=topic)).to_have_count(0)
