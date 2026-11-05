"""Демо-конкурсы (D-054) в настоящем браузере: фазы, анонимность, голос, ничья, письма.

Проверочная среда стартует с пустой базой, поэтому демо-конкурсы создаются при запуске
backend. Тесты, которые голосуют в демо-конкурсе, возвращают его в исходное состояние.
"""

import re
from datetime import timedelta

from playwright.sync_api import expect

from helpers import (
    DEMO_FINISHED,
    DEMO_SUBMISSION,
    DEMO_VOTING,
    EMPLOYEE_NAMES,
    card,
    mark_page,
    assert_not_reloaded,
    parse_time,
    result_row,
    votes_of,
)

ALMATY = timedelta(hours=5)  # часовой пояс браузеров в тестах (conftest)


def test_demo_contests_cover_all_three_phases(people, api):
    phases = {c["topic"]: c["phase"] for c in api("organizer").contests()}
    assert phases[DEMO_SUBMISSION] == "submission"
    assert phases[DEMO_VOTING] == "voting"
    assert phases[DEMO_FINISHED] == "finished"

    org = people("organizer").tab()
    for tab, topic in (("Приём идей", DEMO_SUBMISSION), ("Голосование", DEMO_VOTING), ("Завершены", DEMO_FINISHED)):
        org.get_by_role("tab", name=re.compile(tab)).click()
        expect(org.get_by_role("link", name=re.compile(topic))).to_be_visible()
        others = {DEMO_SUBMISSION, DEMO_VOTING, DEMO_FINISHED} - {topic}
        for other in others:
            expect(org.get_by_role("link", name=re.compile(other))).to_have_count(0)


def test_submission_demo_each_participant_sees_only_own_ideas(people, api):
    contest = api("organizer").contest_by_topic(DEMO_SUBMISSION)
    url = f"/contests/{contest['id']}"

    anna = people("anna").tab(url)
    expect(anna.locator("article[data-idea-id]")).to_have_count(2)
    expect(card(anna, "Живые растения в опенспейсе")).to_be_visible()
    expect(card(anna, "Тихая комната для звонков")).to_be_visible()

    boris = people("boris").tab()
    with boris.expect_response(re.compile(rf"/api/contests/{contest['id']}$")) as response:
        boris.goto(url)
    expect(boris.locator("article[data-idea-id]")).to_have_count(1)
    expect(card(boris, "Пледы и мягкие кресла в зоне отдыха")).to_be_visible()
    # Не только на экране: чужих идей нет и в ответе сервера, который получил браузер.
    assert "Живые растения" not in response.value.text()
    assert [i["title"] for i in api("boris").snapshot(contest["id"])["ideas"]] == ["Пледы и мягкие кресла в зоне отдыха"]

    org = people("organizer").tab(url)
    expect(org.get_by_role("heading", name="Идеи скрыты до начала голосования")).to_be_visible()
    expect(org.locator("[data-test=ideas-count]")).to_have_text("3")
    expect(org.get_by_text("Живые растения")).to_have_count(0)
    assert api("organizer").snapshot(contest["id"])["ideas"] == []


def test_voting_demo_is_anonymous_and_votes_reach_organizer_live(people, api):
    contest = api("organizer").contest_by_topic(DEMO_VOTING)
    url = f"/contests/{contest['id']}"
    favourite, second = "Среда без совещаний", "Повестка за день до встречи"

    anna = people("anna").tab()
    with anna.expect_response(re.compile(rf"/api/contests/{contest['id']}$")) as response:
        anna.goto(url)
    expect(anna.locator("article[data-idea-id]")).to_have_count(4)
    # Авторов нет ни в карточках, ни в ответе сервера.
    cards_text = " ".join(anna.locator("article[data-idea-id]").all_inner_texts())
    assert not any(name in cards_text for name in EMPLOYEE_NAMES)
    assert not any(name in response.value.text() for name in EMPLOYEE_NAMES)
    # За свою идею голосовать нельзя: кнопки нет.
    own = card(anna, "Совещания стоя — не дольше 15 минут")
    expect(own.get_by_text("Ваша идея")).to_be_visible()
    expect(own.get_by_role("button", name="Голосовать")).to_have_count(0)

    org = people("organizer").tab(url)
    expect(org.locator("li[data-idea-id]")).to_have_count(4)
    expect(org.locator("[data-test=author]")).to_have_count(0)
    expect(votes_of(org, favourite)).to_have_text("2")
    mark_page(org)

    try:
        # Голос за несколько идей сразу.
        card(anna, favourite).get_by_role("button", name="Голосовать").click()
        expect(card(anna, favourite).get_by_text("Вы проголосовали")).to_be_visible()
        card(anna, second).get_by_role("button", name="Голосовать").click()
        expect(card(anna, second).get_by_text("Вы проголосовали")).to_be_visible()

        expect(votes_of(org, favourite)).to_have_text("3")
        expect(votes_of(org, second)).to_have_text("2")
        assert_not_reloaded(org)
        voted = {i["title"] for i in api("anna").snapshot(contest["id"])["ideas"] if i["voted_by_me"]}
        assert voted == {favourite, second}
        assert api("organizer").idea(contest["id"], favourite)["votes_count"] == 3
    finally:
        # Отзыв — и демо-конкурс снова в исходном состоянии.
        for title in (favourite, second):
            api("anna").revoke(api("anna").idea(contest["id"], title)["id"])

    expect(votes_of(org, favourite)).to_have_text("2")
    expect(votes_of(org, second)).to_have_text("1")
    expect(card(anna, favourite).get_by_role("button", name="Голосовать")).to_be_visible()


def test_finished_demo_tie_is_won_by_earlier_idea(people, api):
    contest = api("organizer").contest_by_topic(DEMO_FINISHED)
    snap = api("boris").snapshot(contest["id"])
    chatbot, microwaves = snap["ideas"][:2]
    assert (chatbot["title"], microwaves["title"]) == ("Предзаказ обедов через чат-бот", "Микроволновки на каждом этаже")
    assert chatbot["votes_count"] == microwaves["votes_count"] == 2
    assert snap["winner_idea_id"] == chatbot["id"]
    earlier, later = parse_time(chatbot["submitted_at"]), parse_time(microwaves["submitted_at"])
    assert later - earlier == timedelta(seconds=27)

    boris = people("boris").tab(f"/contests/{contest['id']}")
    expect(boris.get_by_role("heading", name="Ваша идея победила!")).to_be_visible()
    winner = boris.locator("li.winner")
    expect(winner).to_have_count(1)
    expect(winner.get_by_role("heading", name="Предзаказ обедов через чат-бот")).to_be_visible()
    # Пояснение ничьей — с секундами: обе идеи поданы в одну минуту.
    note = boris.locator("[data-test=tie-note]")
    expect(note).to_contain_text("поданная раньше")
    for moment in (earlier, later):
        expect(note).to_contain_text((moment + ALMATY).strftime("%H:%M:%S"))
    # После финала авторы раскрыты.
    expect(result_row(boris, "Предзаказ обедов через чат-бот").locator("[data-test=author]")).to_have_text("Борис Котов")
    expect(result_row(boris, "Микроволновки на каждом этаже").locator("[data-test=author]")).to_have_text("Вера Орлова")


def test_finished_demo_letters_and_who_can_read_them(people, api):
    contest = api("organizer").contest_by_topic(DEMO_FINISHED)
    winner_subject = f"Ваша идея победила в конкурсе «{DEMO_FINISHED}»"

    boris = people("boris").tab()
    boris.get_by_role("link", name="Входящие").click()
    letter = boris.locator("button[data-letter-id]").filter(has_text=winner_subject)
    expect(letter).to_have_count(1)
    letter.click()
    body = boris.locator("pre.body")
    expect(body).to_contain_text("1. Предзаказ обедов через чат-бот — 2 голоса — автор: Борис Котов")
    expect(body).to_contain_text("При равенстве голосов побеждает идея, поданная раньше.")

    # Во «Входящих» — только свои письма; в журнале рассылки организатора — все (D-063).
    boris_mail = api("boris").emails()
    assert boris_mail and {m["recipient"]["id"] for m in boris_mail} == {api("boris").id}
    organizer_inbox = api("organizer").emails(contest["id"])
    assert {m["recipient"]["id"] for m in organizer_inbox} == {api("organizer").id}
    recipients = {m["recipient"]["id"] for m in api("organizer").journal(contest["id"])}
    assert len(recipients - {api("organizer").id}) == 4
    gleb_kinds = {m["kind"] for m in api("gleb").emails(contest["id"])}
    assert {"reminder_submission", "final"} <= gleb_kinds  # Глеб так и не подал идею

    # Дина в конкурсе не участвует: ни конкурса, ни писем.
    dina = people("dina").tab()
    expect(dina.get_by_role("link", name=re.compile(DEMO_FINISHED))).to_have_count(0)
    dina.goto(f"/contests/{contest['id']}")
    expect(dina.get_by_role("heading", name="Конкурс не найден")).to_be_visible()
    assert api("dina").emails(contest["id"]) == []
    assert api("dina").get(f"/api/contests/{contest['id']}").status == 404
