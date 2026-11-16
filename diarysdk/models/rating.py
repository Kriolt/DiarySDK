import datetime as dt
from typing import Self

from pydantic import Field

from diarysdk.models.common import Schema, Subject


class RatingMe(Schema):
    place: int | None = None
    average_five: float | None = None
    trend: str | None = None
    previous_place: int | None = None
    previous_average_five: float | None = None
    # …_30 — те же величины дневника за 30 дней.
    place_30: int | None = None
    average_five_30: float | None = None
    trend_30: str | None = None
    rank_status_30: str | None = None
    previous_place_30: int | None = None
    previous_average_five_30: float | None = None
    # Сколько учеников стоят выше (их место меньше), см. RatingEntry.
    ahead: int | None = None
    ahead_30: int | None = None


class RatingEntry(Schema):
    """Место в классе. guid — personId одноклассника, тот же, что у него в
    /v1/me, image_id — его imageId (решение владельца проекта). previous_… —
    прошлое место и средний из previousRank дневника, как у me.

    Места дневника плотные: при равном среднем место общее, следом идёт
    следующее без пропуска (два вторых, следом третий). Поэтому ahead —
    сколько учеников в рейтинге стоят выше, то есть с местом меньше: у дневника
    место определяется средним, и это число учеников с более высоким
    средним. ahead + 1 — место «с пропусками» (два вторых, следом четвёртый).
    Нет места — ahead тоже null."""

    place: int | None = None
    average_five: float | None = None
    trend: str | None = None
    is_me: bool = False
    guid: str | None = None
    image_id: int | None = None
    rank_status: str | None = None
    place_30: int | None = None
    average_five_30: float | None = None
    trend_30: str | None = None
    rank_status_30: str | None = None
    attestation_period_id: int | None = None
    period_id: int | None = None
    module_id: int | None = None
    previous_place: int | None = None
    previous_average_five: float | None = None
    previous_place_30: int | None = None
    previous_average_five_30: float | None = None
    ahead: int | None = None
    ahead_30: int | None = None


class Rating(Schema):
    enabled: bool
    date: dt.date | None = None
    # Число учеников в рейтинге, а не наибольшее место: места идут без
    # пропусков (два вторых, следом третий).
    total: int | None = None
    # Средний балл класса — среднее по всем average_five.
    class_average_five: float | None = None
    me: RatingMe | None = None
    class_: list[RatingEntry] | None = Field(default=None, alias="class")

    @classmethod
    def disabled(cls) -> Self:
        """Рейтинг у школы выключен: 200 с enabled: false, остальное null."""
        return cls(enabled=False)


class SubjectRating(Schema):
    """Место и средний самого ученика по предмету. Среднего класса здесь нет:
    в этом ответе дневник его не даёт, а считать его из чужих оценок мы не
    будем. Весь класс по одному предмету — /v1/rating?subject=<id>."""

    subject: Subject
    place: int | None = None
    average_five: float | None = None
    trend: str | None = None
    rank_status: str | None = None
    place_30: int | None = None
    average_five_30: float | None = None
    trend_30: str | None = None
    rank_status_30: str | None = None
    attestation_period_id: int | None = None
    period_id: int | None = None
    module_id: int | None = None


class RatingPoint(Schema):
    date: dt.date | None = None
    place: int | None = None
