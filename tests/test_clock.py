from datetime import UTC, date, datetime

import pytest

from diarysdk import _clock as clock


def test_today_is_moscow_date_not_utc():
    # 21:30 UTC 31 августа — в Москве уже 00:30 1 сентября.
    late_utc = datetime(2026, 8, 31, 21, 30, tzinfo=UTC)

    assert clock.today_msk(now=late_utc) == date(2026, 9, 1)


def test_today_before_moscow_midnight():
    assert clock.today_msk(now=datetime(2026, 8, 31, 20, 59, tzinfo=UTC)) == date(2026, 8, 31)


@pytest.mark.parametrize(
    ("today", "start"),
    [
        (date(2026, 9, 1), date(2026, 9, 1)),
        (date(2026, 10, 24), date(2026, 9, 1)),
        (date(2026, 12, 31), date(2026, 9, 1)),
        (date(2027, 1, 1), date(2026, 9, 1)),
        (date(2027, 8, 31), date(2026, 9, 1)),
    ],
)
def test_school_year_starts_on_first_of_september(today, start):
    assert clock.school_year_start(today) == start


@pytest.mark.parametrize(
    ("today", "monday", "sunday"),
    [
        (date(2026, 10, 24), date(2026, 10, 19), date(2026, 10, 25)),  # суббота
        (date(2026, 10, 19), date(2026, 10, 19), date(2026, 10, 25)),  # понедельник
        (date(2026, 10, 25), date(2026, 10, 19), date(2026, 10, 25)),  # воскресенье
        (date(2026, 12, 30), date(2026, 12, 28), date(2027, 1, 3)),  # через Новый год
    ],
)
def test_week_bounds_monday_to_sunday(today, monday, sunday):
    assert clock.week_bounds(today) == (monday, sunday)
