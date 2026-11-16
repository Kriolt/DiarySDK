from diarysdk._mapping.rating import history, subject_ratings
from diarysdk._wire.rating import RatingRankShort, RatingRankSubject
from tests.fakes import fixture_text, wire_list


def test_subject_ratings_from_fixture():
    items = wire_list(RatingRankSubject, fixture_text("rating_subjects.json"))

    assert [s.model_dump(mode="json") for s in subject_ratings(items)] == [
        {
            "subject": {"id": 101, "name": "Алгебра"},
            "place": 3,
            "average_five": 4.5,
            "trend": "UP",
            "rank_status": "ACTIVE",
            "place_30": 2,
            "average_five_30": 4.6,
            "trend_30": "UP",
            "rank_status_30": "ACTIVE",
            "attestation_period_id": None,
            "period_id": None,
            "module_id": None,
        },
        {
            "subject": {"id": 102, "name": "Физика"},
            "place": None,
            "average_five": None,
            "trend": None,
            "rank_status": None,
            "place_30": None,
            "average_five_30": None,
            "trend_30": None,
            "rank_status_30": None,
            "attestation_period_id": None,
            "period_id": None,
            "module_id": None,
        },
    ]


def test_history_from_fixture():
    items = wire_list(RatingRankShort, fixture_text("rating_short.json"))

    assert [p.model_dump(mode="json") for p in history(items)] == [
        {"date": "2026-10-01", "place": 3},
        {"date": "2026-10-15", "place": 2},
    ]
