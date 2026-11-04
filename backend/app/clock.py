"""Источник времени (D-026).

Весь код берёт «сейчас» только из объекта часов в `app.state.clock`.
В работе это системные часы, в тестах — управляемые `FakeClock`,
поэтому сроки можно проверять без ожидания реального времени.
"""

import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


def _system_now() -> datetime:
    return datetime.now(UTC)


class SystemClock:
    """Системные часы, которые не идут назад (D-057).

    Системное время может скачком уйти назад: так подстраиваются часы виртуальной машины
    Docker (замер на этапе 7: −1,4 с примерно каждые 29 с) или синхронизация времени.
    Тогда фаза конкурса на мгновение вернулась бы к предыдущей, а позже поданная идея
    получила бы более раннее время подачи и выиграла бы ничью (D-008). Поэтому «сейчас»
    не меньше последнего выданного значения: после скачка время ненадолго «стоит»,
    пока системные часы его не догонят. Гарантия — в пределах процесса (backend один, D-014).
    """

    def __init__(self, source: Callable[[], datetime] = _system_now) -> None:
        self._source = source
        self._last: datetime | None = None
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            current = self._source()
            if self._last is None or current > self._last:
                self._last = current
            return self._last


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
