"""Список конкурсов в браузере (D-061): «Ждут вашего действия», участие и счётчики обновляются сами."""

import re

from playwright.sync_api import expect

from helpers import unique


def group(page, title):
    return page.locator("section.list").filter(has=page.get_by_role("heading", name=title, exact=True))


def row(page, topic):
    return page.get_by_role("link", name=re.compile(re.escape(topic)))


def test_row_moves_out_of_action_group_after_submitting(people, api):
    topic = unique("Список: действие")
    api("organizer").create_contest(topic, submission_in=600, voting_in=600, participants=["vera", "gleb"])

    vera = people("vera").tab()
    org = people("organizer").tab()
    expect(group(vera, "Ждут вашего действия").locator(".contest-row", has_text=topic)).to_contain_text("Подайте идею")
    expect(row(org, topic)).to_contain_text("0 идей")
    expect(row(org, topic)).to_contain_text("участников: 2")

    api("vera").submit(next(c["id"] for c in api("vera").contests() if c["topic"] == topic), "Идея Веры")

    # Без перезагрузки: строка Веры ушла в «Идут», у организатора вырос счётчик.
    expect(group(vera, "Идут").locator(".contest-row", has_text=topic)).to_contain_text("Вы подали 1 идею")
    expect(group(vera, "Ждут вашего действия").locator(".contest-row", has_text=topic)).to_have_count(0)
    expect(row(org, topic)).to_contain_text("1 идея")

    # Глеб по-прежнему видит «Подайте идею»: чужая подача ему не раскрывается.
    gleb = people("gleb").tab()
    expect(group(gleb, "Ждут вашего действия").locator(".contest-row", has_text=topic)).to_contain_text("Подайте идею")
