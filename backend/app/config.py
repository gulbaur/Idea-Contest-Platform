"""Настройки приложения из переменных окружения (D-022).

Имя поля = имя переменной окружения без учёта регистра:
`database_url` читается из `DATABASE_URL` и т. д.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "postgresql+asyncpg://contest:contest@db:5432/contest"
    session_ttl_hours: int = 24

    # Публичный пароль демо-аккаунтов: синтетическое значение, не секрет (D-004).
    demo_password: str = "demo-password"
    seed_demo_data: bool = True
