"""Правила пароля и одноразовые ссылки для его задания (D-062)."""

import secrets

from app.security import hash_session_token

MIN_LENGTH = 10
MAX_LENGTH = 256

# Самые частые пароли подходящей длины: такой пароль подбирается первым.
COMMON = {
    "1234567890",
    "12345678910",
    "123456789012",
    "0123456789",
    "1111111111",
    "0987654321",
    "qwertyuiop",
    "qwerty1234",
    "qwerty12345",
    "password12",
    "password123",
    "password1234",
    "passw0rd123",
    "iloveyou12",
    "abc1234567",
    "1q2w3e4r5t",
    "1qaz2wsx3edc",
    "zaq12wsxcde",
    "йцукенгшщз",
    "пароль1234",
    "пароль12345",
    "demo-password",
}


def password_problem(password: str, login: str) -> str | None:
    """Почему пароль не подходит, или None.

    Длина важнее «заглавной и цифры» (современные рекомендации, NIST SP 800-63B):
    не короче 10 символов, не логин и не из списка самых частых паролей.
    """
    if len(password) < MIN_LENGTH:
        return f"Пароль должен быть не короче {MIN_LENGTH} символов"
    if len(password) > MAX_LENGTH:
        return f"Пароль должен быть не длиннее {MAX_LENGTH} символов"
    if password.strip().lower() == login.strip().lower():
        return "Пароль не должен совпадать с логином"
    if password.lower() in COMMON or len(set(password)) < 4:
        return "Этот пароль слишком простой и легко подбирается — выберите другой"
    return None


def new_setup_token() -> tuple[str, str]:
    """Токен ссылки (256 бит) и его хеш для БД: сам токен знает только получатель ссылки."""
    token = secrets.token_urlsafe(32)
    return token, hash_session_token(token)
