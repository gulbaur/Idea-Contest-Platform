"""Полный путь конкурса по настоящему времени (D-055).

Организатор и участники в разных браузерных профилях, у Анны две вкладки. Проверяются
смена фаз без перезагрузки, одновременные действия двух пользователей, удаление идеи
с голосами, ничья в итогах и письма. После каждого шага — фактическое состояние через API.
"""

import re

from playwright.sync_api import expect

from helpers import (
    Barrier,
    assert_not_reloaded,
    card,
    confirm,
    eventually,
    mark_page,
    parse_time,
    phase_badge,
    result_row,
    submit_idea,
    unique,
    votes_of,
    wait_until,
)

SUBMISSION_SECONDS = 40
VOTING_SECONDS = 40

ANNA = "Экскурсии по офису для гостей"
BORIS = "Мастер-классы от сотрудников"
VERA = "Карта офиса для гостей"


def test_contest_from_creation_to_results(people, api):
    org_api = api("organizer")
    topic = unique("День открытых дверей")

    # Все вкладки открыты заранее: новый конкурс должен появиться у участников сам.
    org = people("organizer").tab()
    anna1 = people("anna").tab()
    anna2 = people("anna").tab()
    boris = people("boris").tab()
    vera = people("vera").tab()
    dina = people("dina").tab()

    contest = org_api.create_contest(
        topic,
        submission_in=SUBMISSION_SECONDS,
        voting_in=VOTING_SECONDS,
        participants=["anna", "boris", "vera", "gleb"],
    )
    cid = contest["id"]
    url = f"/contests/{cid}"
    submission_deadline = parse_time(contest["submission_deadline"])
    voting_deadline = parse_time(contest["voting_deadline"])

    contest_link = anna1.get_by_role("link", name=re.compile(re.escape(topic)))
    expect(contest_link).to_be_visible()  # без перезагрузки списка
    expect(boris.get_by_role("link", name=re.compile(re.escape(topic)))).to_be_visible()
    # Дина не участвует: конкурса нет ни в её списке, ни в её API.
    expect(dina.get_by_role("link", name=re.compile(re.escape(topic)))).to_have_count(0)
    assert cid not in {c["id"] for c in api("dina").contests()}

    contest_link.click()
    for page in (org, anna2, boris, vera):
        page.goto(url)
    pages = [org, anna1, anna2, boris, vera]
    for page in pages:
        expect(phase_badge(page)).to_contain_text("Приём идей")
        mark_page(page)

    # --- приём идей -------------------------------------------------------------
    submit_idea(anna1, "Экскурсии по офису", "Сотрудники по очереди водят гостей по офису.")
    expect(card(anna2, "Экскурсии по офису")).to_be_visible()  # вторая вкладка — сама
    submit_idea(boris, BORIS, "Каждый отдел показывает, чем занимается.")
    submit_idea(vera, VERA, "Схема с подписями: где переговорные, кухня и зоны отдыха.")
    submit_idea(vera, "Лишняя идея", "Подана по ошибке.")
    card(vera, "Лишняя идея").get_by_role("button", name="Удалить").click()
    confirm(vera, "Удалить")
    expect(card(vera, "Лишняя идея")).to_have_count(0)
    expect(org.locator("[data-test=ideas-count]")).to_have_text("3")

    # Чужие идеи до голосования не видны — ни на экране, ни в ответе сервера.
    expect(card(boris, "Экскурсии по офису")).to_have_count(0)
    assert [i["title"] for i in api("boris").snapshot(cid)["ideas"]] == [BORIS]
    assert [i["title"] for i in api("vera").snapshot(cid)["ideas"]] == [VERA]
    expect(org.get_by_text("Экскурсии по офису")).to_have_count(0)

    # Правка во второй вкладке Анны видна в первой.
    card(anna2, "Экскурсии по офису").get_by_role("button", name="Изменить").click()
    anna2.locator("section.editing").get_by_label("Название").fill(ANNA)
    anna2.locator("section.editing").get_by_role("button", name="Сохранить").click()
    expect(card(anna1, ANNA)).to_be_visible()
    anna_idea = api("anna").idea(cid, ANNA)
    assert anna_idea["version"] == 2
    assert org_api.snapshot(cid)["contest"]["phase"] == "submission", "сценарий не успел до срока"

    # --- срок приёма: все вкладки сами переходят к голосованию ---------------------
    wait_until(submission_deadline, org_api)
    for page in pages:
        expect(phase_badge(page)).to_contain_text("Голосование")
        assert_not_reloaded(page)
    expect(boris.locator("article[data-idea-id]")).to_have_count(3)  # теперь видны все идеи
    expect(org.locator("li[data-idea-id]")).to_have_count(3)
    # Авторы скрыты до финала — и от участников, и от организатора.
    shown = " ".join(boris.locator("article[data-idea-id]").all_inner_texts())
    shown += " ".join(org.locator("li[data-idea-id]").all_inner_texts())
    assert not any(name in shown for name in ("Анна Смирнова", "Борис Котов", "Вера Орлова"))
    expect(org.locator("[data-test=author]")).to_have_count(0)
    late = api("gleb").post(
        f"/api/contests/{cid}/ideas",
        {"title": "Опоздавшая", "description": "После срока", "client_request_id": "00000000-0000-4000-8000-000000000001"},
    )
    assert late.status == 409  # сервер сам закрыл приём, а не только интерфейс

    # --- одновременно: Борис и Вера голосуют за идею Анны --------------------------
    barrier = Barrier([boris, vera], re.compile(r"/api/ideas/\d+/vote$"))
    card(boris, ANNA).get_by_role("button", name="Голосовать").click()
    card(vera, ANNA).get_by_role("button", name="Голосовать").click()
    barrier.release()
    for page in (boris, vera):
        expect(card(page, ANNA).get_by_text("Вы проголосовали")).to_be_visible()
    expect(votes_of(org, ANNA)).to_have_text("2")
    assert org_api.idea(cid, ANNA)["votes_count"] == 2

    # --- Анна голосует за несколько идей в одной вкладке, отзывает голос в другой ------
    card(anna1, BORIS).get_by_role("button", name="Голосовать").click()
    card(anna1, VERA).get_by_role("button", name="Голосовать").click()
    expect(card(anna2, VERA).get_by_text("Вы проголосовали")).to_be_visible()  # сама
    card(anna2, VERA).get_by_role("button", name="Отозвать").click()
    expect(card(anna1, VERA).get_by_role("button", name="Голосовать")).to_be_visible()
    assert {i["title"] for i in api("anna").snapshot(cid)["ideas"] if i["voted_by_me"]} == {BORIS}

    # --- одновременно: Анна снова голосует за идею Веры, а Вера её удаляет -------------
    card(vera, VERA).get_by_role("button", name="Удалить").click()
    expect(vera.get_by_role("alertdialog")).to_contain_text("вместе со всеми голосами")
    barrier = Barrier([anna1, vera], re.compile(r"/api/ideas/\d+(/vote)?$"), ("POST", "DELETE"))
    card(anna1, VERA).get_by_role("button", name="Голосовать").click()
    confirm(vera, "Удалить")
    barrier.release()
    for page in (anna1, anna2, boris, vera):
        expect(card(page, VERA)).to_have_count(0)
    expect(result_row(org, VERA)).to_have_count(0)
    # Какой бы запрос ни оказался первым, голосов за удалённую идею не осталось.
    snap = org_api.snapshot(cid)
    assert {i["title"] for i in snap["ideas"]} == {ANNA, BORIS}
    assert snap["stats"]["votes_count"] == sum(i["votes_count"] for i in snap["ideas"]) == 3
    assert {i["title"] for i in api("anna").snapshot(cid)["ideas"] if i["voted_by_me"]} == {BORIS}
    expect(org.locator("[data-test=ideas-count]")).to_have_text("2")

    # --- ничья 2:2: лидирует идея, поданная раньше (Анны) ----------------------------
    card(vera, BORIS).get_by_role("button", name="Голосовать").click()
    expect(votes_of(org, BORIS)).to_have_text("2")
    expect(org.locator("[data-test=tie-note]")).to_contain_text("Сейчас лидирует идея, поданная раньше")
    expect(org.locator("li[data-idea-id]").first.get_by_role("heading")).to_have_text(ANNA)
    assert org_api.snapshot(cid)["contest"]["phase"] == "voting", "сценарий не успел до срока"

    # --- срок голосования: итоги у всех без перезагрузки ------------------------------
    wait_until(voting_deadline, org_api)
    for page in pages:
        expect(phase_badge(page)).to_contain_text("Завершён")
        assert_not_reloaded(page)
    expect(anna1.get_by_role("heading", name="Ваша идея победила!")).to_be_visible()
    expect(anna2.get_by_role("heading", name="Ваша идея победила!")).to_be_visible()
    expect(org.locator("li.winner").get_by_role("heading", name=ANNA)).to_be_visible()
    expect(boris.locator("[data-test=tie-note]")).to_contain_text("Победила идея, поданная раньше")
    expect(result_row(boris, ANNA).locator("[data-test=author]")).to_have_text("Анна Смирнова")
    expect(result_row(org, BORIS).locator("[data-test=author]")).to_have_text("Борис Котов")
    final = org_api.snapshot(cid)
    assert final["winner_idea_id"] == anna_idea["id"]
    # После финала ничего изменить нельзя — проверяет сервер.
    assert api("boris").revoke(anna_idea["id"]).status == 409
    assert api("anna").delete(f"/api/ideas/{anna_idea['id']}").status == 409

    # --- письма: итоговые приходят сами -----------------------------------------------
    anna1.get_by_role("link", name="Входящие").click()
    expect(
        anna1.locator("button[data-letter-id]").filter(has_text=f"Ваша идея победила в конкурсе «{topic}»")
    ).to_have_count(1)

    def final_recipients():
        return {m["recipient"]["id"] for m in org_api.journal(cid) if m["kind"] == "final"} - {org_api.id}

    participants = {api(login).id for login in ("anna", "boris", "vera", "gleb")}
    eventually(lambda: final_recipients() == participants)
    # Глеб не подал идею и не голосовал — приглашение, оба напоминания, «голосование открыто» и итоги.
    assert sorted(m["kind"] for m in api("gleb").emails(cid)) == [
        "final", "invitation", "reminder_submission", "reminder_voting", "voting_open",
    ]
    # Организатору — его итоговое письмо и сводки числами (D-063).
    assert {m["kind"] for m in org_api.emails(cid)} >= {"final", "org_submission_closed"}
    assert api("dina").emails(cid) == []
    boris_final = next(m for m in api("boris").emails(cid) if m["kind"] == "final")
    assert f"Победила идея «{ANNA}» (автор: Анна Смирнова, 2 голоса)" in boris_final["body"]
