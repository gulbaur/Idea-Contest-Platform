"""Создание конкурса через интерфейс организатора (F1, D-050)."""

import re
from datetime import timedelta

from playwright.sync_api import expect

from helpers import NAMES, parse_time, unique


def test_organizer_creates_contest_and_participants_see_it(people, api):
    topic = unique("Как встречать новых сотрудников")
    anna = people("anna").tab()
    dina = people("dina").tab()
    org = people("organizer").tab()
    before = {c["id"] for c in api("organizer").contests()}

    org.get_by_role("link", name="Новый конкурс", exact=True).first.click()
    org.get_by_label("Тема конкурса").fill(topic)
    org.get_by_role("button", name="Демо: 3 + 3 мин").click()
    org.locator("label.person", has_text=NAMES["dina"]).click()  # Дина не участвует
    expect(org.get_by_text("выбрано 4 из 5")).to_be_visible()
    org.get_by_role("button", name="Создать конкурс").click()
    dialog = org.get_by_role("alertdialog")
    expect(dialog).to_contain_text("Сроки и список участников после создания изменить нельзя")
    dialog.get_by_role("button", name="Создать").click()
    expect(org.get_by_role("heading", name=topic)).to_be_visible()

    # Участники видят конкурс без перезагрузки, Дина — нет.
    expect(anna.get_by_role("link", name=re.compile(re.escape(topic)))).to_be_visible()
    anna.wait_for_timeout(500)
    expect(dina.get_by_role("link", name=re.compile(re.escape(topic)))).to_have_count(0)

    # Фактическое состояние: ровно один новый конкурс, нужные участники и сроки.
    created = [c for c in api("organizer").contests() if c["id"] not in before]
    assert [c["topic"] for c in created] == [topic]
    contest = created[0]
    assert org.url.endswith(f"/contests/{contest['id']}")
    names = {p["display_name"] for p in api("organizer").get(f"/api/contests/{contest['id']}/participants").json()}
    assert names == {NAMES[u] for u in ("anna", "boris", "vera", "gleb")}
    submission = parse_time(contest["submission_deadline"])
    voting = parse_time(contest["voting_deadline"])
    assert voting - submission == timedelta(minutes=3)
    # Быстрый вариант округляет вверх до минуты: поле ввода не хранит секунды.
    assert timedelta(minutes=3) <= submission - parse_time(contest["created_at"]) < timedelta(minutes=4)
    assert contest["phase"] == "submission"
