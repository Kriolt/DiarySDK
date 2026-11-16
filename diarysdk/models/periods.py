import datetime as dt

from pydantic import JsonValue

from diarysdk.models.common import Schema


class PeriodDay(Schema):
    """День расписания периодов: каникулы, праздники. Форма уточняется по живому ответу."""

    date: dt.date | None = None
    # Как пришёл из дневника, справочника значений нет.
    type: str | None = None
    title: str | None = None
    description: str | None = None
    # Форма неизвестна: отдаётся как пришло, пока живой ответ не покажет её.
    events: JsonValue = None
