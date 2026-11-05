"""Настройки вида в настоящем браузере (D-060): тема следует за пользователем, а не за браузером."""

import re

from playwright.sync_api import expect

from helpers import NAMES


def theme(page):
    return page.evaluate("document.documentElement.dataset.theme")


def test_theme_follows_the_user_not_the_browser(people, api):
    vera = people("vera")
    settings = vera.tab("/settings")
    settings.get_by_text("Тёмная", exact=True).click()
    expect(settings.get_by_role("status").filter(has_text="Сохранено")).to_be_visible()
    assert theme(settings) == "dark"
    settings.get_by_text("IBM Plex Sans", exact=True).click()
    expect(settings.locator("html")).to_have_attribute("data-font", "plex")

    try:
        # Сохранено на сервере: новая вкладка (новый вход) той же сотрудницы — тоже тёмная.
        assert api("vera").get("/api/auth/me").json()["preferences"]["theme"] == "dark"
        second = vera.tab()
        assert theme(second) == "dark"

        # Тот же браузер, соседняя вкладка, другой пользователь — его собственная (светлая) тема.
        other = vera.context.new_page()
        other.goto("/login")
        other.get_by_role("button", name=re.compile(NAMES["gleb"])).click()
        expect(other.get_by_role("heading", name="Конкурсы", exact=True)).to_be_visible()
        expect(other.locator("html")).to_have_attribute("data-theme", "light")
        assert theme(settings) == "dark"  # вкладка Веры не изменилась
        other.close()
    finally:
        api("vera").request.patch(
            "/api/auth/me/preferences",
            headers={"Authorization": f"Bearer {api('vera').token}"},
            data={"theme": "system", "font": "inter"},
        )
