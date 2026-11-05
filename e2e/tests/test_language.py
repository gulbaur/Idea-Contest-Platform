"""Английский язык интерфейса (D-065): выбор в настройках, хранение у пользователя, ответы сервера."""

import re

from playwright.sync_api import expect


def test_switching_to_english_follows_the_user(people, api):
    vera = people("vera")
    page = vera.tab("/settings")
    try:
        page.get_by_text("English", exact=True).click()
        expect(page.get_by_role("heading", name="Settings", exact=True)).to_be_visible()
        expect(page.locator("html")).to_have_attribute("lang", "en")
        expect(page.get_by_role("link", name=re.compile("Inbox"))).to_be_visible()
        expect(page.get_by_text("Online")).to_be_visible()
        page.get_by_role("link", name=re.compile("^Contests")).first.click()
        expect(page.get_by_role("heading", name="Contests", exact=True)).to_be_visible()

        # Язык сохранён у пользователя: новая вкладка после входа — тоже на английском.
        assert api("vera").get("/api/auth/me").json()["preferences"]["locale"] == "en"
        second = vera.context.new_page()
        second.goto("/login")
        expect(second.get_by_role("button", name="Sign in")).to_be_visible()  # язык последнего входа
        second.get_by_label("Login").fill("vera")
        second.get_by_label("Password").fill("неверный")
        second.get_by_role("button", name="Sign in").click()
        # Ошибка от сервера — тоже на английском (Accept-Language).
        expect(second.get_by_text("Incorrect login or password")).to_be_visible()
        second.close()
    finally:
        api("vera").request.patch(
            "/api/auth/me/preferences",
            headers={"Authorization": f"Bearer {api('vera').token}"},
            data={"locale": "ru"},
        )
