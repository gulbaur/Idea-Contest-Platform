# Матрица требований

Источники: **Т** — раздел «Требования» задания; **О** — «Что мы ожидаем от вас»; **З7** — «Задание 7. Конкурс идей»; **П** — уточнения пользователя ([PROMPTS.md](PROMPTS.md), запись 1).

Статусы: ⬜ не начато · 🟡 частично / в работе · ✅ выполнено и подтверждено проверкой · ❌ не выполнено.
Статус ✅ ставится только при наличии запущенной проверки или другого свидетельства.

Последнее обновление: этап 3 (2026-10-31).

## Общие требования

| ID | Требование | Источник | Реализация | Проверка / свидетельство | Статус |
|---|---|---|---|---|---|
| G1 | Отдельные backend и frontend, общаются по сети | Т1, П | — | — | ⬜ |
| G2 | Backend: Python + FastAPI; причины выбора описаны | Т2, П | причины — DECISIONS D-001 | — | 🟡 |
| G3 | Frontend: Vue 3 + Vite (JavaScript) | Т3, П | решение — D-001, D-002 | — | ⬜ |
| G4 | Реляционная СУБД — PostgreSQL | Т4 | `compose.yaml` (postgres:17), `backend/app/models.py`, миграции `backend/migrations` | `test_migrations_match_models`; все тесты идут на PostgreSQL | 🟡 (таблицы конкурса — этапы 2–5) |
| G5 | Модель учётных записей и входа выбрана и описана | Т5, П | D-003, D-004, D-023; `backend/app/api/auth.py`, `deps.py`, `security.py` | `tests/test_auth.py` (17 тестов), `tests/test_security.py` | ✅ |
| G6 | Промпты / лог решений сданы с кодом | Т6 | PROMPTS.md, DECISIONS.md, DEVELOPMENT_LOG.md | файлы в репозитории | 🟡 |
| G7 | Использование AI описано открыто | Т7 | AI_USAGE.md | — | 🟡 |
| G8 | Предварительные требования для развёртывания описаны | Т8 | README «Предварительные требования» | — | 🟡 (дополнится frontend; финальная проверка — приёмка) |
| G9 | Быстрый локальный запуск (Docker Compose) | Т9, П | `compose.yaml`, `backend/Dockerfile`; миграции и демо-данные при старте | `docker compose up --build -d --wait` → db и backend healthy (журнал, этап 1) | 🟡 (без frontend) |
| G10 | Внешние сервисы эмулированы (почта) | Т10, П | решение — D-016 | — | ⬜ |
| G11 | Работает при двух одновременно открытых клиентах | Т11, П | — | — | ⬜ |
| G12 | Честное описание состояния проекта | Т12, П | README «Текущее состояние» | — | 🟡 |
| G13 | Доказуемость работоспособности | Т13, П | тесты backend, журнал проверок; проверка тестов поломкой кода | 144 теста после исправлений по проверке качества (журнал, REVIEW.md) | 🟡 |

## Ожидаемые результаты сдачи

| ID | Требование | Источник | Реализация | Проверка / свидетельство | Статус |
|---|---|---|---|---|---|
| E1 | Ссылка на репозиторий GitHub | О1 | публикация по команде пользователя | — | ⬜ |
| E2 | Модель и инструмент и почему (пара предложений) | О2 | AI_USAGE.md | инструмент, модель и причины записаны со слов пользователя | ✅ |
| E3 | Промпты, лог решений или экспорт сессии | О3 | PROMPTS.md, DEVELOPMENT_LOG.md, DECISIONS.md | — | 🟡 |
| E4 | Ход работы во времени | О4 | DEVELOPMENT_LOG.md с системными отметками, история коммитов | — | 🟡 |
| E5 | Описание: как развернуть и в каком состоянии | О5 | README | — | 🟡 |
| E6 | Что сделали бы следующим заходом | О6 | README | — | ⬜ |
| E7 | Указаны заимствованные шаблоны и генераторы | О7 | AI_USAGE.md | — | 🟡 |

## Функциональные требования «Конкурс идей»

| ID | Требование | Источник | Реализация | Проверка / свидетельство | Статус |
|---|---|---|---|---|---|
| F1 | Конкурс: тема, срок закрытия приёма идей, срок закрытия голосования | З7, П | `POST /api/contests` (`backend/app/api/contests.py`), таблицы `contests`, `contest_participants` (D-009, D-032) | `tests/test_contests.py`: создание, проверка сроков и участников, идемпотентность, параллельное создание | 🟡 (API готов; интерфейс — этап 6) |
| F2 | Подача идеи с названием и описанием | З7 | `POST /api/contests/{id}/ideas` (`backend/app/api/ideas.py`), таблица `ideas`; несколько идей от участника (D-006) | `test_participant_submits_idea`, `test_participant_may_submit_several_ideas`, `test_idea_validation` | 🟡 (API готов; интерфейс — этап 6) |
| F3 | Правка своей идеи до закрытия приёма | З7, П | `PUT /api/ideas/{id}` с `version`; `submitted_at` не меняется (D-008, D-031) | `test_author_edits_idea_before_deadline_keeping_submitted_at`, `test_edit_rejected_exactly_at_deadline_and_later`, `test_stale_version_from_other_tab_is_rejected_with_current_data`, `test_cannot_edit_someone_elses_idea` | 🟡 (API готов; интерфейс — этап 6) |
| F4 | Голосование: список идей без авторов | З7 | — | — | ⬜ |
| F5 | Один голос на идею от человека, сколько бы вкладок ни было открыто | З7, П | первичный ключ `votes (idea_id, voter_id)` + `ON CONFLICT DO NOTHING` (D-033, D-034); за разные идеи — можно | `test_parallel_identical_votes_create_one_vote` (10 параллельных запросов), `test_two_tabs_of_same_user_still_one_vote`, `test_database_itself_rejects_duplicate_vote`, `test_participant_can_vote_for_several_different_ideas`; поломка кода (без ON CONFLICT) — БД всё равно отвергла дубль | 🟡 (API; интерфейс — этап 6) |
| F6 | Финал: результаты, авторы раскрываются | З7 | снимок конкурса в фазе «финал»: авторы, `votes_count`, порядок, `winner_idea_id` (D-035) | `test_everyone_sees_results_and_winner_after_final`, `test_finished_everyone_sees_authors` | 🟡 (API; интерфейс — этап 6) |
| F7 | Финал: письмо победителю и всем участникам, без дубля для победителя | З7, П | решение — D-012 | — | ⬜ |
| F8 | Экран организатора: число идей, число проголосовавших людей, текущие результаты | З7, П | `stats` (участники, идеи, `voters_count` = COUNT DISTINCT, голоса) и счёт идей во время голосования (D-035, D-037) | `test_organizer_sees_live_results_during_voting`, `test_voters_count_counts_people_not_votes`, `test_deleting_idea_removes_its_votes_atomically` | 🟡 (данные — да; экран — этап 6) |
| F9 | Раунды закрываются сами в назначенное время | З7 | решение — D-007, D-015 | — | ⬜ |
| F10 | Идея/правка после закрытия приёма и голос/отзыв после закрытия голосования не принимаются, даже со старой страницы | З7, П | фаза вычисляется по серверному времени после блокировки конкурса (D-007, D-029) | `test_submission_closes_exactly_at_deadline`, `test_stale_page_cannot_submit_after_deadline`, `test_edit_rejected_exactly_at_deadline_and_later`, `test_phase_boundaries` | 🟡 (идеи — да; голоса — этап 3) |
| F11 | Во время подачи чужие идеи не видны (API и WebSocket) | З7, П | фильтр в SQL-запросе снимка (D-028); WS — сигналы без данных (D-014) | `test_submission_participant_sees_only_own_ideas` (проверяется весь текст JSON), `test_submission_organizer_sees_only_counters` | 🟡 (API — да; WebSocket — этап 4) |
| F12 | Во время голосования видны все идеи без авторов | З7 | снимок конкурса в фазе «голосование» (D-028) | `test_voting_everyone_sees_all_ideas_without_authors` (участник, участник без идей, организатор; имена авторов не встречаются в JSON) | 🟡 (API готов; интерфейс — этап 6) |
| F13 | За свою идею проголосовать нельзя (сервер) | З7, П | проверка `idea.author_id` в `POST /api/ideas/{id}/vote` (D-034) | `test_cannot_vote_for_own_idea`; поломка кода — тест упал | ✅ (сервер) |
| F14 | Голос можно отозвать до закрытия голосования | З7 | `DELETE /api/ideas/{id}/vote`, фаза по серверному времени (D-034) | `test_revoke_before_deadline_and_rejected_after`, `test_repeated_revoke_and_vote_again` | 🟡 (API; интерфейс — этап 6) |
| F15 | Организатор видит изменения результатов без обновления страницы | З7 | решение — D-014 | — | ⬜ |
| F16 | Остальные видят результаты только после финала | З7 | `votes_count`, статистика и победитель скрыты от участников до финала (D-035); порядок идей — по подаче | `test_results_hidden_from_participants_during_voting`, `test_voting_stats_only_for_organizer` | 🟡 (API; WebSocket — этап 4) |
| F17 | Одно напоминание за сутки до закрытия раунда только тем, кто не участвовал | З7, П | решение — D-010, D-015 | — | ⬜ |
| F18 | При ничьей побеждает более ранняя идея; правило видно заранее | З7, П | `ranking_key` (голоса → `submitted_at` → id), `submitted_at` не меняется при правке (D-008, D-035); текст правила — README и интерфейс (этап 6) | `test_tie_is_won_by_earlier_idea_even_after_edit`, `test_tie_with_identical_submit_time_is_won_by_lower_id`, `test_no_votes_means_earliest_idea_wins`, `test_no_ideas_means_no_winner`, `test_ranking.py`; поломка правила — 3 теста упали | 🟡 (правило — да; показ участникам в интерфейсе — этап 6) |
| F19 | Удалённая во время голосования идея исчезает у всех сразу вместе с отданными за неё голосами | З7, П | `DELETE /api/ideas/{id}` под блокировкой конкурса; голоса — `ON DELETE CASCADE` в той же транзакции (D-011, D-029, D-033) | `test_deleting_idea_removes_its_votes_atomically`, `test_parallel_vote_and_delete_leave_no_orphan_votes` (5 повторов) | 🟡 (удаление с голосами — да; «сразу у всех» — WebSocket, этап 4) |

## Дополнительные требования пользователя

| ID | Требование | Источник | Реализация | Проверка / свидетельство | Статус |
|---|---|---|---|---|---|
| P1 | Серверная идентичность, демо-аккаунты; роль и id не берутся от клиента | П | D-003; `get_current_user` в `backend/app/deps.py`; `backend/app/seed.py` | `test_client_cannot_spoof_identity_or_role`, `test_me_requires_valid_token`, `test_seed_is_idempotent` | ✅ (backend) |
| P2 | Две вкладки: один пользователь и разные пользователи; описано в README | П | D-003; отдельная сессия на каждый вход; README «Проверка двумя клиентами» | `test_two_tabs_of_same_user_are_independent_sessions`, `test_two_tabs_of_different_users_do_not_affect_each_other` | 🟡 (API готов; sessionStorage во frontend — этап 6) |
| P3 | Уникальность голосов ограничением БД; повторные запросы идемпотентны | П | PK `votes`; `client_request_id` для конкурсов и идей; повтор голоса, отзыва и правки без эффекта (D-006, D-013, D-031, D-033, D-034) | `test_database_itself_rejects_duplicate_vote`, `test_parallel_identical_votes_create_one_vote`, `test_parallel_identical_submits_create_one_idea`, `test_parallel_identical_create_requests_create_one_contest`, `test_revision_changes_only_when_vote_state_changes` | ✅ (backend) |
| P4 | Публикация после коммита; переподключение; защита от устаревших ответов | П | решение — D-014 | — | ⬜ |
| P5 | Задания и записи об исполнении в PostgreSQL; работа после перезапуска без повторов | П | решение — D-015 | — | ⬜ |
| P6 | `REMINDER_LEAD` (по умолчанию 24 ч); демо-конкурсы во всех фазах; быстрый конкурс | П | решение — D-015 | — | ⬜ |
| P7 | Интерфейс с состояниями загрузки, ошибок, пустых списков | П | — | — | ⬜ |
| P8 | Тесты на PostgreSQL, управляемые часы, браузерные E2E, одна команда | П | D-025, D-026; `backend/tests/conftest.py`, `FakeClock` | `docker compose --profile test run --rm --build tests` → 144 passed (исправления по проверке качества); `test_session_expires_exactly_at_expires_at` | 🟡 (E2E — этап 7) |
| P9 | `.gitattributes` с LF; кроссплатформенные инструкции | П | `.gitattributes` (D-018); команды README одинаковы для всех ОС, где различаются — даны варианты | `git check-attr`, `git ls-files --eol` — журнал этапов 0–1 | 🟡 (проверка на Linux/macOS — приёмка) |
| P10 | Документация: README, REQUIREMENTS, DECISIONS, DEVELOPMENT_LOG, PROMPTS, AI_USAGE, CLAUDE.md, PLAN | П | файлы созданы на этапе 0 | — | 🟡 |
| P11 | Правила поведения зафиксированы до реализации (пустой конкурс, границы, гонки, роль организатора, удаление, состав получателей) | П | DECISIONS D-005 … D-016 | — | ✅ |
