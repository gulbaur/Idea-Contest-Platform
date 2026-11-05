"""Ответы сервера на языке интерфейса (D-065).

Код пишет сообщения об ошибках по-русски, как и раньше. Если клиент прислал
`Accept-Language: en`, обработчик ошибок (app/main.py) переводит текст по этому словарю.
Тест test_i18n.py находит в коде каждое сообщение об ошибке и проверяет, что у него есть перевод.
"""

import re

EXACT: dict[str, str] = {
    # вход и доступ
    "Требуется вход": "Sign-in required",
    "Неверный логин или пароль": "Incorrect login or password",
    "Текущий пароль указан неверно": "The current password is incorrect",
    "Новый пароль совпадает с текущим": "The new password is the same as the current one",
    "Пароль не должен совпадать с логином": "The password must not be the same as the login",
    "Этот пароль слишком простой и легко подбирается — выберите другой":
        "This password is too common and easy to guess — choose another one",
    "Ссылка недействительна или устарела — попросите администратора выдать новую":
        "The link is invalid or has expired — ask an administrator for a new one",
    "Действие доступно только организатору": "Only an organizer can do this",
    "Действие доступно только администратору": "Only an administrator can do this",
    # сотрудники
    "Сотрудник не найден": "Employee not found",
    "Такой логин уже занят": "This login is already taken",
    "Такая почта уже есть у другого сотрудника": "Another employee already has this email",
    "Такой логин или почта уже заняты": "This login or email is already taken",
    "Нельзя изменить собственную роль — попросите другого администратора":
        "You cannot change your own role — ask another administrator",
    "Это последний администратор: без него управлять сотрудниками будет некому":
        "This is the last administrator: without them nobody could manage people",
    "Нельзя отключить себя — попросите другого администратора":
        "You cannot disable yourself — ask another administrator",
    "Доступ сотрудника отключён — сначала включите его": "This employee's access is disabled — enable it first",
    "Логин: 2–64 символа — латинские буквы, цифры, точка, дефис, подчёркивание":
        "Login: 2–64 characters — Latin letters, digits, dot, hyphen, underscore",
    "Укажите рабочую почту в виде name@company.com": "Enter a work email like name@company.com",
    # конкурсы, идеи, голоса
    "Конкурс не найден": "Contest not found",
    "Идея не найдена": "Idea not found",
    "Срок окончания приёма идей должен быть в будущем": "The idea submission deadline must be in the future",
    "Срок окончания голосования должен быть позже окончания приёма идей":
        "The voting deadline must be later than the submission deadline",
    "Нет сотрудников для участия в конкурсе": "There are no employees to take part in the contest",
    "Организатор не подаёт идеи": "Organizers do not submit ideas",
    "Приём идей закрыт": "Idea submission is closed",
    "Приём идей закрыт: идею больше нельзя изменить": "Idea submission is closed: the idea can no longer be edited",
    "Конкурс завершён: идею больше нельзя удалить": "The contest is finished: the idea can no longer be deleted",
    "Идея с этим запросом только что изменилась — обновите страницу":
        "The idea for this request has just changed — reload the page",
    "Идея уже изменена в другой вкладке": "The idea has already been changed in another tab",
    "Этот запрос уже выполнен с другими данными — повторно ничего не создано":
        "This request was already made with different data — nothing was created again",
    "Организатор не голосует": "Organizers do not vote",
    "Голосование ещё не началось": "Voting has not started yet",
    "Голосование закрыто": "Voting is closed",
    "Нельзя голосовать за свою идею": "You cannot vote for your own idea",
    "Текст содержит недопустимый символ NUL": "The text contains a forbidden NUL character",
    # почта
    "Письмо не найдено": "Email not found",
    "Журнал рассылки доступен организатору и администратору":
        "The mailing log is available to organizers and administrators",
    "before_time и before_id передаются вместе": "before_time and before_id must be sent together",
    # прочее
    "База данных недоступна": "The database is unavailable",
}

PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"^Слишком много неудачных попыток входа\. Попробуйте снова через (\d+) мин\.$"),
        r"Too many failed sign-in attempts. Try again in \1 min.",
    ),
    (
        re.compile(r"^Участниками могут быть только сотрудники; неверные id: (.*)$", re.S),
        r"Only employees can take part; invalid ids: \1",
    ),
    (re.compile(r"^Пароль должен быть не короче (\d+) символов$"), r"The password must be at least \1 characters long"),
    (re.compile(r"^Пароль должен быть не длиннее (\d+) символов$"), r"The password must be at most \1 characters long"),
    (
        re.compile(r"^Роль можно сменить после завершения конкурсов, где сотрудник участвует: (.*)$", re.S),
        r"The role can be changed once the contests this employee takes part in are finished: \1",
    ),
]


def wants_english(accept_language: str | None) -> bool:
    """Первый язык из заголовка Accept-Language — английский (интерфейс шлёт ровно «en» или «ru»)."""
    first = (accept_language or "").split(",")[0].strip().lower()
    return first.startswith("en")


def translate(text: str) -> str:
    """Русское сообщение → английское; неизвестный текст возвращается как есть."""
    if text in EXACT:
        return EXACT[text]
    for pattern, replacement in PATTERNS:
        if pattern.match(text):
            return pattern.sub(replacement, text)
    return text
