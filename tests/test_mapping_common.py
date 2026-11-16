"""Разбор дат и времени из ответов дневника."""

from datetime import UTC, date, datetime

import pytest

from diarysdk._clock import MOSCOW
from diarysdk._mapping.common import as_datetime, as_int


def test_as_datetime_treats_bare_date_as_moscow_midnight():
    assert as_datetime(date(2026, 10, 24)) == datetime(2026, 10, 24, tzinfo=MOSCOW)


def test_as_datetime_date_string_matches_date_object():
    assert as_datetime("2026-10-24") == as_datetime(date(2026, 10, 24))


def test_as_datetime_keeps_zone_and_defaults_naive_to_moscow():
    aware = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)
    assert as_datetime(aware) == aware
    naive = datetime(2026, 10, 24, 9, 0)  # noqa: DTZ001 - проверяем именно наивное время
    assert as_datetime(naive).tzinfo == MOSCOW


def test_as_datetime_garbage_is_none():
    assert as_datetime("не дата") is None
    assert as_datetime(None) is None


@pytest.mark.parametrize("value", ["--5", "²", "-", "5-", "1_000", "٣x", "1.5"])
def test_as_int_of_non_int_string_is_none_not_error(value):
    assert as_int(value) is None


@pytest.mark.parametrize(("value", "expected"), [("-5", -5), (" 7 ", 7), ("0", 0), (3.0, 3)])
def test_as_int_accepts_ints(value, expected):
    assert as_int(value) == expected
