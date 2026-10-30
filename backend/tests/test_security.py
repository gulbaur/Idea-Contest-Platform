"""Модульные тесты хеширования паролей и токенов (без БД)."""

from app.security import (
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)


def test_password_hash_roundtrip():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)


def test_same_password_gives_different_hashes_because_of_salt():
    assert hash_password("same") != hash_password("same")


def test_malformed_stored_hash_is_rejected_without_error():
    assert not verify_password("x", "not-a-hash")
    assert not verify_password("x", "bcrypt$1$2$3$AAAA$BBBB")
    assert not verify_password("x", "scrypt$abc$8$1$AAAA$BBBB")


def test_session_tokens_are_unique_and_hash_is_deterministic():
    first, second = new_session_token(), new_session_token()
    assert first != second
    assert hash_session_token(first) == hash_session_token(first)
    assert len(hash_session_token(first)) == 64
