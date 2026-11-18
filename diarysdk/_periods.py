"""Периоды запросов: значения по умолчанию и проверка длины.

Общие для ядра и сервера: «сегодня» считается по Москве (_clock).
"""

from datetime import date, timedelta

from diarysdk import _clock as clock
from diarysdk.errors import BadRequest


def resolve_period(
    start: date | None,
    end: date | None,
    *,
    default_start: date,
    default_end: date,
    span: int | None = None,
    max_days: int | None = None,
) -> tuple[date, date]:
    """Границы периода; длина считается включительно.

    span — сколько дней от данной границы до недостающей: дали только начало
    недели расписания — конец ставится через 6 дней, а не берётся из текущей
    недели (иначе начало оказалось бы позже конца).
    """
    if span is not None and start is not None and end is None:
        end = start + timedelta(days=span)
    elif span is not None and end is not None and start is None:
        start = end - timedelta(days=span)
    start = start or default_start
    end = end or default_end
    if start > end:
        raise BadRequest("Начало периода (from) позже конца (to)")
    if max_days is not None and (end - start).days + 1 > max_days:
        raise BadRequest(f"Период длиннее {max_days} дней")
    return start, end


def schedule_period(start: date | None, end: date | None, today: date) -> tuple[date, date]:
    """Расписание: по умолчанию текущая неделя, не больше 31 дня."""
    monday, sunday = clock.week_bounds(today)
    return resolve_period(start, end, default_start=monday, default_end=sunday, span=6, max_days=31)


def homework_period(start: date | None, end: date | None, today: date) -> tuple[date, date]:
    """Домашние задания: по умолчанию от сегодня на неделю вперёд."""
    return resolve_period(
        start,
        end,
        default_start=today,
        default_end=today + timedelta(days=7),
        span=7,
        max_days=31,
    )


def marks_period(start: date | None, end: date | None, today: date) -> tuple[date, date]:
    """Оценки: по умолчанию с начала учебного года по сегодня.

    Один конец (`to` в прошлом году) — начало берётся от учебного года этого конца.
    """
    return resolve_period(
        start,
        end,
        default_start=clock.school_year_start(end or today),
        default_end=today,
        max_days=366,
    )


def rating_history_period(start: date | None, end: date | None, today: date) -> tuple[date, date]:
    """История рейтинга: с начала учебного года по сегодня, без предела длины."""
    return resolve_period(
        start, end, default_start=clock.school_year_start(end or today), default_end=today
    )


def school_periods_period(start: date | None, end: date | None, today: date) -> tuple[date, date]:
    """Учебные периоды: по умолчанию весь текущий учебный год.

    Задан один край — берётся учебный год этого края, а не текущий.
    """
    year_start = clock.school_year_start(end or start or today)
    return resolve_period(
        start,
        end,
        default_start=year_start,
        default_end=date(year_start.year + 1, 8, 31),
        max_days=366,
    )


def final_marks_year(year: int | None, today: date) -> int:
    """Учебный год итоговых оценок: по умолчанию текущий, будущего нет."""
    current = clock.school_year_start(today).year
    if year is None:
        return current
    if year > current:
        raise BadRequest("Этот учебный год ещё не начался")
    return year


def journal_period(start: date | None, end: date | None, today: date) -> tuple[date, date]:
    """Ознакомление: по умолчанию текущая неделя, начало — понедельник своей недели,
    не больше 31 дня."""
    monday, sunday = clock.week_bounds(today)
    # Дневник отдаёт недели целиком: начало сдвигаем на понедельник до проверки длины.
    if start is not None:
        start = clock.week_bounds(start)[0]
    return resolve_period(start, end, default_start=monday, default_end=sunday, span=6, max_days=31)
