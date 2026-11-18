"""Ознакомление с дневником: ответ aware_journals → JournalAck."""

from datetime import date, datetime
from typing import Any

from pydantic import TypeAdapter, ValidationError

from diarysdk import _clock as clock
from diarysdk._mapping.common import as_date
from diarysdk._wire.web import AwareJournal
from diarysdk.errors import UpstreamFormat
from diarysdk.models.parent import JournalAck

# Формат времени отметки у сайта и дневника: «03.02.2026 10:15».
STAMP = "%d.%m.%Y %H:%M"

_LIST = TypeAdapter(list[AwareJournal])


def stamp(moment: datetime) -> str:
    return clock.now_msk(moment).strftime(STAMP)


def _created(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, STAMP).replace(tzinfo=clock.MOSCOW)
    except ValueError:
        return None


def acks(data: Any) -> list[JournalAck]:
    try:
        items = _LIST.validate_python(data)
    except ValidationError as error:
        raise UpstreamFormat.from_validation(error) from None
    result = []
    for item in items:
        week = as_date(item.week)
        if week is None or item.student_profile_id is None:
            continue
        result.append(
            JournalAck(
                week=week, created_at=_created(item.created_at), child_id=item.student_profile_id
            )
        )
    return result


def has_week(items: list[JournalAck], child_id: int, monday: date) -> bool:
    return any(ack.week == monday and ack.child_id == child_id for ack in items)
