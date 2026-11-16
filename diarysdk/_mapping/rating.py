"""Рейтинг из ej/rating/v1/rank/*. personId выходит как guid, imageId — как
image_id. Значения «за 30 дней» и ID периодов модель ответа не объявляет,
они читаются через field() по ключам дневника. ahead дневник не даёт —
он считается из мест."""

from datetime import date
from typing import Any

from pydantic import TypeAdapter, ValidationError

from diarysdk._mapping.common import as_date, as_float, as_int, as_text, field
from diarysdk._wire.rating import RatingRankClass, RatingRankShort, RatingRankSubject
from diarysdk.errors import UpstreamFormat
from diarysdk.models.common import Subject
from diarysdk.models.rating import Rating, RatingEntry, RatingMe, RatingPoint, SubjectRating

_CLASS_RANKS = TypeAdapter(list[RatingRankClass])


def class_ranks(data: Any) -> list[RatingRankClass]:
    """Сырой ответ rank/class (рейтинг по предмету идёт своим запросом) —
    в модели ответа, чтобы дальше работал тот же rating()."""
    try:
        return _CLASS_RANKS.validate_python(data)
    except ValidationError as error:
        raise UpstreamFormat.from_validation(error) from None


def _rank_extra(rank: Any) -> dict[str, Any]:
    """Поля ранга сверх места, среднего и тренда — общие у класса и предметов."""
    return {
        "rank_status": as_text(field(rank, "rank_status")),
        "place_30": as_int(field(rank, "rankPlace30")),
        "average_five_30": as_float(field(rank, "averageMarkFive30")),
        "trend_30": as_text(field(rank, "trend30")),
        "rank_status_30": as_text(field(rank, "rankStatus30")),
        "attestation_period_id": as_int(field(rank, "attestationPeriodId")),
        "period_id": as_int(field(rank, "periodId")),
        "module_id": as_int(field(rank, "moduleId")),
    }


def _ahead(place: int | None, places: list[int | None]) -> int | None:
    """Сколько учеников стоят выше: место дневника плотное (два вторых, следом
    третий), и по нему одному не видно, сколько человек впереди."""
    if place is None:
        return None
    return sum(1 for other in places if other is not None and other < place)


def rating(ranks: list[RatingRankClass], me_guid: str, on: date) -> Rating:
    places = [item.rank.rank_place if item.rank else None for item in ranks]
    places_30 = [as_int(field(item.rank, "rankPlace30")) for item in ranks]
    entries = []
    me = None
    for item in ranks:
        rank = item.rank
        previous = item.previous_rank
        extra = _rank_extra(rank)
        entry = RatingEntry(
            place=rank.rank_place if rank else None,
            average_five=rank.average_mark_five if rank else None,
            trend=rank.trend if rank else None,
            is_me=item.person_id == me_guid,
            guid=item.person_id,
            image_id=item.image_id,
            previous_place=previous.rank_place if previous else None,
            previous_average_five=previous.average_mark_five if previous else None,
            previous_place_30=as_int(field(previous, "rankPlace30")),
            previous_average_five_30=as_float(field(previous, "averageMarkFive30")),
            ahead=_ahead(rank.rank_place if rank else None, places),
            ahead_30=_ahead(extra["place_30"], places_30),
            **extra,
        )
        entries.append(entry)
        if entry.is_me:
            me = RatingMe(
                place=entry.place,
                average_five=entry.average_five,
                trend=entry.trend,
                previous_place=entry.previous_place,
                previous_average_five=entry.previous_average_five,
                place_30=entry.place_30,
                average_five_30=entry.average_five_30,
                trend_30=entry.trend_30,
                rank_status_30=entry.rank_status_30,
                previous_place_30=entry.previous_place_30,
                previous_average_five_30=entry.previous_average_five_30,
                ahead=entry.ahead,
                ahead_30=entry.ahead_30,
            )
    # sorted устойчив: при равных местах порядок дневника сохраняется.
    entries.sort(key=lambda e: (e.place is None, e.place or 0))
    averages = [e.average_five for e in entries if e.average_five is not None]
    return Rating(
        enabled=True,
        date=on,
        total=len(ranks),
        class_average_five=round(sum(averages) / len(averages), 2) if averages else None,
        me=me,
        class_=entries,
    )


def subject_ratings(items: list[RatingRankSubject]) -> list[SubjectRating]:
    return [
        SubjectRating(
            subject=Subject(id=item.subject_id, name=item.subject_name),
            place=item.rank.rank_place,
            average_five=item.rank.average_mark_five,
            trend=item.rank.trend,
            **_rank_extra(item.rank),
        )
        for item in items
    ]


def history(items: list[RatingRankShort]) -> list[RatingPoint]:
    return [RatingPoint(date=as_date(item.date), place=item.rank_place) for item in items]
