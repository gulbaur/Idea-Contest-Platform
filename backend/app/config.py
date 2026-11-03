"""Настройки приложения из переменных окружения (D-022).

Имя поля = имя переменной окружения без учёта регистра:
`database_url` читается из `DATABASE_URL` и т. д.
"""

from datetime import timedelta

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "postgresql+asyncpg://contest:contest@db:5432/contest"
    session_ttl_hours: int = 24

    # Публичный пароль демо-аккаунтов: синтетическое значение, не секрет (D-004).
    demo_password: str = "demo-password"
    seed_demo_data: bool = True

    # WebSocket (D-039, D-040): сколько ждать сообщения со входом; сколько сигналов
    # может ждать отправки одному клиенту; как долго фоновая задача сроков может спать.
    ws_auth_timeout_seconds: float = 5.0
    ws_queue_limit: int = 100
    deadline_max_sleep_seconds: float = 30.0

    # За сколько до окончания раунда напоминать (D-046): «ЧЧ:ММ:СС» или ISO 8601 (PT2M).
    # По умолчанию сутки, как в задании; меньшее значение — только для демонстрации.
    reminder_lead: timedelta = Field(default=timedelta(hours=24), gt=timedelta(0))
    # Как долго обработчик заданий может спать между проверками (D-043).
    jobs_max_sleep_seconds: float = 30.0
