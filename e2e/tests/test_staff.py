"""Сотрудники и доступ в браузере (D-062): приглашение, первый вход по ссылке, участие, отключение."""

import re
import uuid

from playwright.sync_api import expect

from helpers import BASE_URL, unique

PASSWORD = "надёжная-фраза-2026"


def test_invited_employee_joins_contest_and_is_cut_off_when_disabled(people, browser, api):
    login = f"e2e-{uuid.uuid4().hex[:8]}"
    name = "Елена Ким"

    # Администратор приглашает сотрудника и получает одноразовую ссылку.
    admin = people("admin").tab()
    admin.get_by_role("button", name="Пригласить сотрудника").click()
    admin.get_by_label("Имя и фамилия").fill(name)
    admin.get_by_label("Логин").fill(login)
    admin.get_by_label("Рабочая почта").fill(f"{login}@example.com")
    admin.get_by_role("button", name="Пригласить", exact=True).click()
    link = admin.locator("#setup-link").input_value()
    assert re.fullmatch(rf"{re.escape(BASE_URL)}/setup#[\w-]{{40,}}", link), link
    admin.get_by_role("button", name="Готово").click()
    expect(admin.locator(f'[data-login="{login}"]')).to_contain_text("Приглашён")

    # Сотрудник в своём браузере открывает ссылку, задаёт пароль и сразу входит.
    context = browser.new_context(base_url=BASE_URL, viewport={"width": 1366, "height": 900}, locale="ru-RU")
    try:
        newcomer = context.new_page()
        newcomer.goto(link)
        expect(newcomer.get_by_role("heading", name=f"Здравствуйте, {name}!")).to_be_visible()
        assert "#" not in newcomer.url  # токен убран из адресной строки
        newcomer.get_by_label("Пароль", exact=True).fill(PASSWORD)
        newcomer.get_by_label("Пароль ещё раз").fill(PASSWORD)
        newcomer.get_by_role("button", name="Задать пароль и войти").click()
        expect(newcomer.get_by_role("heading", name="Конкурсы", exact=True)).to_be_visible()
        expect(newcomer.get_by_text("Онлайн")).to_be_visible()

        # Повторно ссылкой воспользоваться нельзя.
        again = context.new_page()
        again.goto(link)
        expect(again.get_by_role("heading", name="Ссылка недействительна")).to_be_visible()
        again.close()

        # Организатор может включить нового сотрудника в конкурс — и тот видит его без перезагрузки.
        topic = unique("Конкурс для новичка")
        api("organizer").create_contest(topic, submission_in=600, voting_in=600, participants=[login])
        expect(newcomer.get_by_role("link", name=re.compile(re.escape(topic)))).to_be_visible()

        # Отключение: открытая вкладка сотрудника выходит сразу, войти снова нельзя.
        admin.locator(f'[data-login="{login}"]').get_by_role("button").click()
        admin.get_by_role("button", name="Отключить доступ").click()
        admin.get_by_role("alertdialog").get_by_role("button", name="Отключить доступ").click()
        expect(admin.locator(f'[data-login="{login}"]')).to_contain_text("Отключён")

        expect(newcomer).to_have_url(re.compile(r"/login"))
        newcomer.get_by_label("Логин").fill(login)
        newcomer.get_by_label("Пароль").fill(PASSWORD)
        newcomer.get_by_role("button", name="Войти").click()
        expect(newcomer.get_by_text("Неверный логин или пароль")).to_be_visible()

        # В журнале действий — всё, что произошло. Окно сотрудника остаётся открытым с новым состоянием.
        admin.get_by_role("dialog").get_by_role("button", name="Закрыть").click()
        admin.get_by_role("tab", name="Журнал действий").click()
        for action in ("Доступ отключён", "Пароль задан по ссылке", "Приглашение"):
            expect(admin.get_by_text(action, exact=True).first).to_be_visible()
    finally:
        context.close()
