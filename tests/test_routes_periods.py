from datetime import date

from diarysdk.models.periods import PeriodDay


async def test_periods_default_is_school_year(api, fake_diary):
    fake_diary.answers["periods"] = [PeriodDay(title="Каникулы", date=date(2026, 10, 26))]

    response = await api.get("/v1/periods")

    assert response.status_code == 200
    assert response.json() == [
        {
            "date": "2026-10-26",
            "type": None,
            "title": "Каникулы",
            "description": None,
            "events": None,
        }
    ]
    _, start, end = fake_diary.args["periods"]
    assert (start, end) == (date(2026, 9, 1), date(2027, 8, 31))


async def test_periods_explicit_bounds(api, fake_diary):
    fake_diary.answers["periods"] = []

    response = await api.get("/v1/periods", params={"from": "2026-10-01", "to": "2026-10-31"})

    assert response.status_code == 200
    assert fake_diary.args["periods"][1:] == (date(2026, 10, 1), date(2026, 10, 31))


async def test_366_days_is_allowed(api, fake_diary):
    fake_diary.answers["periods"] = []

    response = await api.get("/v1/periods", params={"from": "2027-09-01", "to": "2028-08-31"})

    assert response.status_code == 200


async def test_367_days_is_bad_request(api, fake_diary):
    fake_diary.answers["periods"] = []

    response = await api.get("/v1/periods", params={"from": "2027-09-01", "to": "2028-09-01"})

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert "periods" not in fake_diary.calls


async def test_from_after_to_is_bad_request(api, fake_diary):
    response = await api.get("/v1/periods", params={"from": "2026-10-02", "to": "2026-10-01"})

    assert response.status_code == 400
    assert fake_diary.calls == []


async def test_periods_end_only_in_past_year_starts_that_school_year(api, fake_diary):
    fake_diary.answers["periods"] = []

    response = await api.get("/v1/periods", params={"to": "2026-05-31"})

    assert response.status_code == 200
    assert fake_diary.args["periods"][1:] == (date(2025, 9, 1), date(2026, 5, 31))
