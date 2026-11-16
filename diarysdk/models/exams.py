import datetime as dt

from diarysdk.models.common import Schema


class Exam(Schema):
    """Результат ГИА. Форма ответа портала уточняется по живому ответу."""

    # ОГЭ / ЕГЭ / пробный — как пишет портал.
    kind: str | None = None
    subject: str | None = None
    date: dt.date | None = None
    score: int | float | None = None
    mark: str | None = None
