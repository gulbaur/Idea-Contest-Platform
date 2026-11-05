"""Ответы на языке интерфейса (D-065): у каждого сообщения об ошибке в коде есть перевод."""

import ast
import re
from pathlib import Path

import pytest

from app.i18n import translate, wants_english
from tests.helpers import auth, create_contest, login

pytestmark = pytest.mark.usefixtures("demo_users")

APP = Path(__file__).resolve().parent.parent / "app"
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
# Вызовы, текст которых уходит пользователю как сообщение об ошибке.
ERROR_CALLS = {"not_found", "forbidden", "conflict", "_invalid", "_invalid_password", "_conflict", "ValueError", "HTTPException"}
# Не ошибки для пользователя: тексты писем и демо-данные (письма переводятся отдельно), часы тестов.
SKIP_FILES = {"jobs.py", "demo.py", "seed.py", "clock.py", "mail_texts.py"}


def _sample(node: ast.AST) -> str | None:
    """Строка или f-строка как пример текста: подстановки заменены на «1»."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value if isinstance(part, ast.Constant) else "1" for part in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):  # "…: " + ", ".join(...)
        left = _sample(node.left)
        return None if left is None else left + "1"
    return None


def _error_texts() -> list[tuple[str, str]]:
    found = []
    for path in sorted(APP.rglob("*.py")):
        if path.name in SKIP_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # Константы-сообщения вроде LINK_INVALID = "…" и значения "message" в словарях ответа.
            values = []
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if name in ERROR_CALLS:
                    values += list(node.args) + [kw.value for kw in node.keywords if kw.arg in ("detail", None)]
            elif isinstance(node, ast.Dict):
                values += [v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant) and k.value == "message"]
            elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets):
                values.append(node.value)
            elif isinstance(node, ast.Return) and path.name == "passwords.py":
                values.append(node.value)
            elif isinstance(node, ast.arguments):  # значения по умолчанию: not_found(detail="…")
                values += node.defaults
            for value in values:
                text = _sample(value) if value is not None else None
                if text and CYRILLIC.search(text):
                    found.append((f"{path.name}:{value.lineno}", text))
    return found


def test_scanner_finds_the_messages():
    texts = {text for _, text in _error_texts()}
    assert "Неверный логин или пароль" in texts
    assert "Нельзя голосовать за свою идею" in texts
    assert len(texts) > 40


@pytest.mark.parametrize(("where", "text"), _error_texts())
def test_every_error_message_has_an_english_translation(where, text):
    assert not CYRILLIC.search(translate(text)), f"{where}: нет перевода для «{text}»"


def test_accept_language_parsing():
    assert wants_english("en")
    assert wants_english("en-GB,en;q=0.9,ru;q=0.8")
    assert not wants_english("ru")
    assert not wants_english(None)
    assert not wants_english("ru-RU,en;q=0.5")


async def test_errors_come_in_the_interface_language(client):
    ru = await client.post("/api/auth/login", json={"login": "anna", "password": "неверный"})
    assert ru.json()["detail"] == "Неверный логин или пароль"
    en = await client.post(
        "/api/auth/login", json={"login": "anna", "password": "неверный"}, headers={"Accept-Language": "en"}
    )
    assert en.json()["detail"] == "Incorrect login or password"
    assert (await client.get("/api/auth/me", headers={"Accept-Language": "en"})).json()["detail"] == "Sign-in required"


async def test_structured_and_validation_errors_are_translated_too(client, user_ids):
    organizer = await login(client, "organizer")
    contest = await create_contest(client, organizer)
    payload = {"topic": "Тема", "submission_deadline": "2020-01-01T00:00:00Z", "voting_deadline": "2020-01-02T00:00:00Z",
               "client_request_id": "00000000-0000-4000-8000-000000000777"}
    past = await client.post("/api/contests", json=payload, headers={**auth(organizer), "Accept-Language": "en"})
    assert past.json()["detail"] == "The idea submission deadline must be in the future"

    admin = await login(client, "admin")
    bad = await client.post(
        "/api/admin/users",
        json={"login": "Ю", "display_name": "X", "email": "x@example.com"},
        headers={**auth(admin), "Accept-Language": "en"},
    )
    assert bad.status_code == 422
    assert not CYRILLIC.search(bad.json()["detail"][0]["msg"])
    assert contest["id"]  # конкурс создан — ответ на русском без заголовка не пострадал
