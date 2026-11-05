"""Уведомления в браузере (D-063): приглашение без перезагрузки, счётчик непрочитанных, журнал."""

import re

from playwright.sync_api import expect

from helpers import unique


def test_invitation_arrives_live_and_unread_counter_follows(people, api):
    vera = people("vera").tab()
    inbox_link = vera.get_by_role("link", name=re.compile("Входящие"))
    before = api("vera").get("/api/emails/unread-count").json()["count"]

    topic = unique("Уведомления")
    api("organizer").create_contest(topic, submission_in=600, voting_in=600, participants=["vera"])

    # Без перезагрузки: в меню вырос счётчик, во «Входящих» — приглашение.
    expect(inbox_link.locator(".nav-badge")).to_have_text(str(before + 1))
    inbox_link.click()
    letter = vera.locator("button[data-letter-id]").filter(has_text=topic)
    expect(letter).to_have_class(re.compile("unread"))
    letter.click()
    expect(vera.locator("pre.body")).to_contain_text(f"Вас включили в конкурс идей «{topic}»")
    expect(letter).not_to_have_class(re.compile("unread"))
    if before:
        expect(inbox_link.locator(".nav-badge")).to_have_text(str(before))
    else:
        expect(inbox_link.locator(".nav-badge")).to_have_count(0)

    # Организатор: в своих «Входящих» приглашений нет, в журнале рассылки — есть.
    org = people("organizer").tab("/journal")
    expect(org.get_by_role("heading", name="Журнал рассылки")).to_be_visible()
    org.get_by_placeholder("Получатель: имя или адрес").fill("Вера")
    row = org.locator("[data-journal-id]").filter(has_text=topic)
    expect(row).to_contain_text("Приглашение")
    assert all(m["kind"] != "invitation" for m in api("organizer").emails())

    # Участнице журнал недоступен — ни в меню, ни по прямой ссылке.
    expect(vera.get_by_role("link", name="Журнал рассылки")).to_have_count(0)
    assert api("vera").get("/api/emails/journal").status == 403
