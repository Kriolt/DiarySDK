from datetime import date

import pytest

from diarysdk._periods import resolve_period
from diarysdk.errors import BadRequest

D = date


def test_defaults_when_nothing_given():
    assert resolve_period(None, None, default_start=D(2026, 9, 1), default_end=D(2026, 10, 24)) == (
        D(2026, 9, 1),
        D(2026, 10, 24),
    )


def test_given_bounds_win_over_defaults():
    assert resolve_period(
        D(2026, 10, 1), D(2026, 10, 5), default_start=D(2026, 9, 1), default_end=D(2026, 10, 24)
    ) == (D(2026, 10, 1), D(2026, 10, 5))


def test_span_derives_missing_end_from_given_start():
    # Неделя расписания: дали понедельник следующей недели — до воскресенья.
    assert resolve_period(
        D(2026, 10, 26), None, default_start=D(2026, 10, 19), default_end=D(2026, 10, 25), span=6
    ) == (D(2026, 10, 26), D(2026, 11, 1))


def test_span_derives_missing_start_from_given_end():
    assert resolve_period(
        None, D(2026, 10, 18), default_start=D(2026, 10, 19), default_end=D(2026, 10, 25), span=6
    ) == (D(2026, 10, 12), D(2026, 10, 18))


def test_start_after_end_is_bad_request():
    with pytest.raises(BadRequest) as info:
        resolve_period(
            D(2026, 10, 5), D(2026, 10, 1), default_start=D(2026, 9, 1), default_end=D(2026, 10, 24)
        )

    assert (info.value.http_status, info.value.code) == (400, "bad_request")


def test_period_longer_than_limit_is_bad_request():
    # 1 сентября — 31 августа следующего года — 365 дней включительно.
    assert resolve_period(
        D(2026, 9, 1),
        D(2027, 8, 31),
        default_start=D(2026, 9, 1),
        default_end=D(2026, 10, 24),
        max_days=366,
    )
    with pytest.raises(BadRequest) as info:
        resolve_period(
            D(2026, 9, 1),
            D(2027, 9, 2),
            default_start=D(2026, 9, 1),
            default_end=D(2026, 10, 24),
            max_days=366,
        )

    assert info.value.code == "bad_request"


def test_limit_counts_days_inclusively():
    assert resolve_period(
        D(2026, 10, 1),
        D(2026, 10, 31),
        default_start=D(2026, 10, 1),
        default_end=D(2026, 10, 1),
        max_days=31,
    )
    with pytest.raises(BadRequest):
        resolve_period(
            D(2026, 10, 1),
            D(2026, 11, 1),
            default_start=D(2026, 10, 1),
            default_end=D(2026, 10, 1),
            max_days=31,
        )


def test_default_periods_by_scenario():
    from diarysdk import _periods

    today = D(2026, 10, 24)  # суббота

    assert _periods.schedule_period(None, None, today) == (D(2026, 10, 19), D(2026, 10, 25))
    assert _periods.homework_period(None, None, today) == (D(2026, 10, 24), D(2026, 10, 31))
    assert _periods.marks_period(None, None, today) == (D(2026, 9, 1), today)
    assert _periods.rating_history_period(None, None, today) == (D(2026, 9, 1), today)
    assert _periods.school_periods_period(None, None, today) == (D(2026, 9, 1), D(2027, 8, 31))


def test_final_marks_year():
    from diarysdk import _periods

    today = D(2026, 10, 24)

    assert _periods.final_marks_year(None, today) == 2026
    assert _periods.final_marks_year(2024, today) == 2024
    with pytest.raises(BadRequest):
        _periods.final_marks_year(2027, today)


def test_end_only_in_past_year_takes_start_from_that_school_year():
    from diarysdk import _periods

    today = D(2026, 10, 24)
    end = D(2026, 5, 31)

    assert _periods.marks_period(None, end, today) == (D(2025, 9, 1), end)
    assert _periods.rating_history_period(None, end, today) == (D(2025, 9, 1), end)
    assert _periods.school_periods_period(None, end, today) == (D(2025, 9, 1), end)
    # В текущем году всё как раньше.
    assert _periods.marks_period(None, D(2026, 10, 1), today) == (D(2026, 9, 1), D(2026, 10, 1))


def test_start_only_for_school_periods_ends_with_that_school_year():
    from diarysdk import _periods

    today = D(2026, 10, 24)

    assert _periods.school_periods_period(D(2025, 10, 1), None, today) == (
        D(2025, 10, 1),
        D(2026, 8, 31),
    )
    assert _periods.school_periods_period(D(2026, 9, 15), None, today) == (
        D(2026, 9, 15),
        D(2027, 8, 31),
    )
