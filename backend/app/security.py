"""Пароли и токены сессий (D-023). Только стандартная библиотека Python."""

import base64
import hashlib
import hmac
import secrets

# Параметры scrypt: n=2**14, r=8 — около 16 МБ памяти и десятков миллисекунд на проверку.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    """Хеш пароля в формате `scrypt$n$r$p$соль$хеш`; соль случайная для каждого вызова."""
    salt = secrets.token_bytes(_SALT_BYTES)
    key = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_KEY_BYTES
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(key)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, key_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(key_b64)
        actual = hashlib.scrypt(
            password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except ValueError:
        return False
    # Сравнение за постоянное время: не выдаёт по таймингу, сколько байт совпало.
    return hmac.compare_digest(actual, expected)


# Хеш-пустышка: проверяется, когда логин не найден, чтобы ответ занимал
# столько же времени, сколько при неверном пароле (нельзя подобрать логины по таймингу).
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


def new_session_token() -> str:
    """Случайный токен (256 бит), который получает клиент."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """То, что хранится в БД вместо токена."""
    return hashlib.sha256(token.encode()).hexdigest()
