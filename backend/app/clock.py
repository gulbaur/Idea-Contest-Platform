"""Источник времени (D-026).

Весь код берёт «сейчас» только из объекта часов в `app.state.clock`.
В работе это системные часы, в тестах — управляемые `FakeClock`,
поэтому сроки можно проверять без ожидания реального времени.
"""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """Часы для тестов: стоят на месте, пока их явно не передвинут."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FakeClock требует время с часовым поясом")
        self._now = start

    def now(self) -> datetime:
        return self._now

    def set(self, value: datetime) -> None:
        self._now = value

    def advance(self, delta: timedelta) -> None:
        self._now += delta
