"""Системные часы не идут назад (D-057)."""

from datetime import UTC, datetime, timedelta

from app.clock import SystemClock

T = datetime(2026, 11, 4, 8, 46, tzinfo=UTC)


def test_clock_does_not_go_back_after_system_time_jump():
    # Как в виртуальной машине Docker: часы спешат и раз в ~29 с отскакивают на −1,4 с.
    readings = iter([T, T + timedelta(seconds=2), T + timedelta(seconds=0.6), T + timedelta(seconds=1.9), T + timedelta(seconds=3)])
    clock = SystemClock(source=lambda: next(readings))

    seen = [clock.now() for _ in range(5)]

    assert seen == [
        T,
        T + timedelta(seconds=2),
        T + timedelta(seconds=2),  # скачок назад — время «стоит»
        T + timedelta(seconds=2),
        T + timedelta(seconds=3),  # системные часы догнали — снова идут
    ]
    assert seen == sorted(seen)


def test_system_clock_is_real_time_with_timezone():
    clock = SystemClock()
    first, second = clock.now(), clock.now()
    assert first.tzinfo is not None
    assert first <= second
    assert abs(first - datetime.now(UTC)) < timedelta(seconds=5)
