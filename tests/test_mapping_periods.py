from diarysdk._mapping.periods import periods
from diarysdk._wire.mobile import PeriodsSchedules
from tests.fakes import fixture_text, wire_list


def mapped(text=None):
    parsed = wire_list(PeriodsSchedules, text or fixture_text("periods_schedules.json"))
    return [p.model_dump(mode="json") for p in periods(parsed)]


def test_days_with_literal_values_and_events_as_came():
    assert mapped() == [
        {
            "date": "2026-10-26",
            "type": "vacation",
            "title": "Осенние каникулы",
            "description": "Каникулы 26.10 - 01.11",
            "events": [{"id": 1, "title": "Каникулы"}],
        },
        {
            "date": "2026-11-04",
            "type": "holiday",
            "title": "День народного единства",
            "description": None,
            "events": None,
        },
    ]


def test_empty_list():
    assert mapped("[]") == []
