"""Одновременные действия (D-055): запросы двух вкладок отпускаются барьером разом.

Проверяется не только то, что на экране, но и фактическое состояние через API: сколько
голосов записано, какая версия идеи сохранилась, совпадает ли картина во всех вкладках.
"""

import re
import time

import pytest
from playwright.sync_api import expect

from helpers import Barrier, Link, card, parse_time, unique, votes_of, wait_until

VOTE_URL = re.compile(r"/api/ideas/\d+/vote$")


@pytest.fixture(scope="module")
def voting_contest(api) -> dict:
    """Конкурс в фазе голосования с идеями Бориса и Веры."""
    org_api = api("organizer")
    contest = org_api.create_contest(unique("Одновременные голоса"), submission_in=6, voting_in=900)
    for title in ("Идея для двойного голоса", "Идея для голоса и отзыва"):
        api("boris").submit(contest["id"], title)
    api("vera").submit(contest["id"], "Идея Веры")
    wait_until(parse_time(contest["submission_deadline"]), org_api)
    return contest


def anna_votes(api, contest_id: int) -> set[str]:
    return {i["title"] for i in api("anna").snapshot(contest_id)["ideas"] if i["voted_by_me"]}


def test_same_vote_from_two_tabs_at_once_counts_once(people, api, voting_contest):
    cid, title = voting_contest["id"], "Идея для двойного голоса"
    url = f"/contests/{cid}"
    first, second = people("anna").tab(url), people("anna").tab(url)
    org = people("organizer").tab(url)

    barrier = Barrier([first, second], VOTE_URL)
    for page in (first, second):
        card(page, title).get_by_role("button", name="Голосовать").click()
    barrier.release()

    for page in (first, second):
        expect(card(page, title).get_by_text("Вы проголосовали")).to_be_visible()
    expect(votes_of(org, title)).to_have_text("1")
    assert api("organizer").idea(cid, title)["votes_count"] == 1  # база не дала второй голос
    assert title in anna_votes(api, cid)


def test_vote_and_revoke_from_two_tabs_at_once_agree(people, api, voting_contest):
    """Первая вкладка отзывает голос, а вторая — с устаревшим видом — голосует. Одновременно."""
    cid, title = voting_contest["id"], "Идея для голоса и отзыва"
    url = f"/contests/{cid}"
    links: list[Link] = []
    first = people("anna").tab(url)
    second = people("anna").tab(url, before=lambda page: links.append(Link(page)))
    links[0].hold_signals()  # вторая вкладка пока не узнаёт об изменениях
    card(first, title).get_by_role("button", name="Голосовать").click()
    expect(card(first, title).get_by_text("Вы проголосовали")).to_be_visible()
    expect(card(second, title).get_by_role("button", name="Голосовать")).to_be_visible()  # устаревший вид

    barrier = Barrier([first, second], VOTE_URL, ("POST", "DELETE"))
    card(first, title).get_by_role("button", name="Отозвать").click()
    card(second, title).get_by_role("button", name="Голосовать").click()
    with first.expect_response(VOTE_URL), second.expect_response(VOTE_URL):
        barrier.release()
        links[0].release_signals()

    # Какой бы ни была очередь, обе вкладки показывают то, что записано в базе.
    voted = title in anna_votes(api, cid)
    for page in (first, second):
        if voted:
            expect(card(page, title).get_by_text("Вы проголосовали")).to_be_visible()
        else:
            expect(card(page, title).get_by_role("button", name="Голосовать")).to_be_visible()
    assert api("organizer").idea(cid, title)["votes_count"] == (1 if voted else 0)


def test_two_people_vote_at_once_both_count(people, api, voting_contest):
    cid, title = voting_contest["id"], "Идея Веры"
    url = f"/contests/{cid}"
    anna, gleb = people("anna").tab(url), people("gleb").tab(url)
    org = people("organizer").tab(url)
    before = api("organizer").idea(cid, title)["votes_count"]

    barrier = Barrier([anna, gleb], VOTE_URL)
    for page in (anna, gleb):
        card(page, title).get_by_role("button", name="Голосовать").click()
    barrier.release()

    expect(votes_of(org, title)).to_have_text(str(before + 2))
    snap = api("organizer").snapshot(cid)
    assert next(i for i in snap["ideas"] if i["title"] == title)["votes_count"] == before + 2
    assert snap["stats"]["voters_count"] >= 2


def test_same_idea_saved_from_two_tabs_at_once(people, api):
    contest = api("organizer").create_contest(unique("Одновременная правка"), submission_in=600, voting_in=600)
    idea = api("anna").submit(contest["id"], "Исходное название", "Исходный текст")
    url = f"/contests/{contest['id']}"
    first, second = people("anna").tab(url), people("anna").tab(url)

    for page, title in ((first, "Название из первой вкладки"), (second, "Название из второй вкладки")):
        card(page, "Исходное название").get_by_role("button", name="Изменить").click()
        page.locator("section.editing").get_by_label("Название").fill(title)

    barrier = Barrier([first, second], re.compile(rf"/api/ideas/{idea['id']}$"), ("PUT",))
    for page in (first, second):
        page.locator("section.editing").get_by_role("button", name="Сохранить").click()
    barrier.release()

    # Отпущенные запросы ещё идут к серверу: ждём, пока правка сохранится, а не читаем сразу.
    deadline = time.monotonic() + 10
    while not (
        saved := api("anna").idea(contest["id"], "Название из первой вкладки")
        or api("anna").idea(contest["id"], "Название из второй вкладки")
    ):
        assert time.monotonic() < deadline, "ни одна правка не сохранилась"
        time.sleep(0.1)
    assert saved["version"] == 2  # сохранилась ровно одна правка
    loser = second if saved["title"] == "Название из первой вкладки" else first
    # Проигравшая вкладка не перезаписала чужую правку: показала конфликт и актуальный текст.
    expect(loser.get_by_text("Идею уже изменили в другой вкладке")).to_be_visible()
    expect(loser.locator("section.editing").get_by_label("Название")).to_have_value(saved["title"])
    assert len(api("anna").snapshot(contest["id"])["ideas"]) == 1
