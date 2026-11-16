"""Время по Москве: «сегодня», «текущая неделя» и «с начала учебного года».

Дневник и ученики живут по Москве; по UTC «сегодня» с 21:00 до полуночи было
бы вчерашним днём.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")


def now_msk(now: datetime | None = None) -> datetime:
    return (now or datetime.now(MOSCOW)).astimezone(MOSCOW)


def today_msk(now: datetime | None = None) -> date:
    return now_msk(now).date()


def school_year_start(today: date) -> date:
    """1 сентября текущего учебного года."""
    year = today.year if today.month >= 9 else today.year - 1
    return date(year, 9, 1)


def week_bounds(today: date) -> tuple[date, date]:
    """Понедельник и воскресенье недели, в которую попадает today."""
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)
