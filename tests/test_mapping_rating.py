from datetime import date

from diarysdk._mapping.rating import rating
from diarysdk._wire.rating import RatingRankClass
from diarysdk.models.rating import Rating
from tests.fakes import GUID, fixture_text, wire_list

ON = date(2026, 10, 24)


def ranks(text=None):
    return wire_list(RatingRankClass, text or fixture_text("rating_class.json"))


def test_rating_from_fixture():
    result = rating(ranks(), GUID, ON).model_dump(mode="json")

    assert result == {
        "enabled": True,
        "date": "2026-10-24",
        "total": 4,
        "class_average_five": 4.5,
        "me": {
            "place": 2,
            "average_five": 4.5,
            "trend": "DOWN",
            "previous_place": 1,
            "previous_average_five": 4.6,
            # …_30 — те же величины дневника за 30 дней.
            "place_30": 3,
            "average_five_30": 4.4,
            "trend_30": "UP",
            "rank_status_30": "ACTIVE",
            "previous_place_30": 2,
            "previous_average_five_30": 4.5,
            # Впереди один: место плотное, второе делят двое.
            "ahead": 1,
            "ahead_30": 1,
        },
        # По месту; при равенстве два вторых, следом третий, без пропусков.
        # guid — personId из рейтинга, у самого ученика он тот же, что в /v1/me.
        "class": [
            {
                "place": 1,
                "average_five": 4.9,
                "trend": "NONE",
                "is_me": False,
                "guid": "00000000-0000-4000-8000-0000000000c1",
                "image_id": 9101,
                "rank_status": "ACTIVE",
                "place_30": 1,
                "average_five_30": 4.9,
                "trend_30": "NONE",
                "rank_status_30": "ACTIVE",
                "attestation_period_id": None,
                "period_id": None,
                "module_id": None,
                "previous_place": 1,
                "previous_average_five": 4.9,
                "previous_place_30": 1,
                "previous_average_five_30": 4.9,
                "ahead": 0,
                "ahead_30": 0,
            },
            {
                "place": 2,
                "average_five": 4.5,
                "trend": "DOWN",
                "is_me": True,
                "guid": "00000000-0000-4000-8000-000000000001",
                "image_id": 9102,
                "rank_status": "ACTIVE",
                "place_30": 3,
                "average_five_30": 4.4,
                "trend_30": "UP",
                "rank_status_30": "ACTIVE",
                "attestation_period_id": None,
                "period_id": None,
                "module_id": None,
                "previous_place": 1,
                "previous_average_five": 4.6,
                "previous_place_30": 2,
                "previous_average_five_30": 4.5,
                "ahead": 1,
                "ahead_30": 1,
            },
            {
                # В этой записи дневник не дал значений за 30 дней и прошлого
                # места (previousRank: null) — null.
                "place": 2,
                "average_five": 4.5,
                "trend": "UP",
                "is_me": False,
                "guid": "00000000-0000-4000-8000-0000000000c2",
                "image_id": None,
                "rank_status": "ACTIVE",
                "place_30": None,
                "average_five_30": None,
                "trend_30": None,
                "rank_status_30": None,
                "attestation_period_id": None,
                "period_id": None,
                "module_id": None,
                "previous_place": None,
                "previous_average_five": None,
                "previous_place_30": None,
                "previous_average_five_30": None,
                "ahead": 1,
                "ahead_30": None,
            },
            {
                "place": 3,
                "average_five": 4.1,
                "trend": "UP",
                "is_me": False,
                "guid": "00000000-0000-4000-8000-0000000000c3",
                "image_id": 9103,
                "rank_status": "ACTIVE",
                "place_30": 3,
                "average_five_30": 4.0,
                "trend_30": "UP",
                "rank_status_30": "ACTIVE",
                "attestation_period_id": None,
                "period_id": None,
                "module_id": None,
                "previous_place": 3,
                "previous_average_five": 4.0,
                "previous_place_30": 3,
                "previous_average_five_30": 4.0,
                # Место третье, а впереди трое: второе делят двое.
                "ahead": 3,
                "ahead_30": 1,
            },
        ],
    }


def test_ahead_counts_everyone_above_dense_place():
    # Места дневника плотные: два вторых, следом третий. Сколько человек
    # впереди, по месту не видно, поэтому ahead считает их сам.
    result = rating(ranks(), GUID, ON)

    assert [(e.place, e.ahead) for e in result.class_] == [(1, 0), (2, 1), (2, 1), (3, 3)]


def test_unconfirmed_rank_fields_tolerate_unexpected_types():
    # periodId и moduleId в наблюдениях всегда null — тип не подтверждён.
    text = (
        fixture_text("rating_class.json")
        .replace('"periodId": null', '"periodId": "p-1"', 1)
        .replace('"rankPlace30": 3', '"rankPlace30": "3"', 1)
    )

    result = rating(ranks(text), GUID, ON)

    entry = next(e for e in result.class_ if e.guid.endswith("c3"))
    assert entry.period_id is None
    assert entry.place_30 == 3


def test_me_is_null_when_not_in_rating():
    assert rating(ranks(), "чужой-guid", ON).me is None


def test_empty_rating_has_no_average():
    result = rating([], GUID, ON)

    assert result.total == 0
    assert result.class_average_five is None
    assert result.class_ == []


def test_disabled_rating_is_all_null():
    assert Rating.disabled().model_dump(mode="json", by_alias=True) == {
        "enabled": False,
        "date": None,
        "total": None,
        "class_average_five": None,
        "me": None,
        "class": None,
    }
