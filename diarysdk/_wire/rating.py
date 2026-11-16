"""Ответы рейтинга (api/ej/rating/v1/rank/*). Ключи дневника — camelCase."""

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

from diarysdk._wire.common import DT, Wire


class _RatingWire(Wire):
    """Поля пишутся в snake_case, а читаются по camelCase-ключам дневника."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Rank(_RatingWire):
    average_mark_five: float | None = None
    rank_place: int | None = None
    rank_status: str | None = None
    trend: str | None = None


class PreviousRank(_RatingWire):
    average_mark_five: float | None = None
    rank_place: int | None = None


class RatingRankClass(_RatingWire):
    person_id: str | None = None
    rank: Rank | None = None
    previous_rank: PreviousRank | None = None
    image_id: int | None = None


class RatingRankShort(_RatingWire):
    date: DT | None = None
    rank_place: int | None = None


class RatingRankSubject(_RatingWire):
    subject_id: int
    subject_name: str
    rank: Rank
