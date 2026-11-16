from datetime import date

import pytest

from diarysdk.models.common import Subject
from diarysdk.models.marks import FinalMark


async def test_marks_default_period_is_school_year_to_today(api, fake_diary):
    fake_diary.answers["marks"] = []

    response = await api.get("/v1/marks")

    assert response.status_code == 200
    assert response.json() == []
    assert fake_diary.args["marks"][1:] == (date(2026, 9, 1), date(2026, 10, 24))


async def test_marks_for_given_period(api, fake_diary):
    fake_diary.answers["marks"] = []

    await api.get("/v1/marks", params={"from": "2026-10-01", "to": "2026-10-10"})

    assert fake_diary.args["marks"][1:] == (date(2026, 10, 1), date(2026, 10, 10))


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-13-01"},
        {"from": "вчера"},
        {"from": "2026-10-10", "to": "2026-10-01"},
        {"from": "2025-09-01", "to": "2026-09-02"},
    ],
)
async def test_bad_period_is_bad_request_without_diary_call(api, fake_diary, params):
    response = await api.get("/v1/marks", params=params)

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert fake_diary.calls == []


async def test_final_marks_default_year_is_current_school_year(api, fake_diary):
    fake_diary.answers["final_marks"] = [
        FinalMark(subject=Subject(id=1, name="Алгебра"), year_mark="7")
    ]

    response = await api.get("/v1/final-marks")

    assert response.status_code == 200
    assert response.json() == [
        {
            "subject": {"id": 1, "name": "Алгебра"},
            "year_mark": "7",
            "attestation_mark": None,
            "training_camp_mark": None,
        }
    ]
    assert fake_diary.args["final_marks"][1:] == (2026,)


async def test_final_marks_for_past_year(api, fake_diary):
    fake_diary.answers["final_marks"] = []

    await api.get("/v1/final-marks", params={"year": "2024"})

    assert fake_diary.args["final_marks"][1:] == (2024,)


@pytest.mark.parametrize("year", ["2027", "2012", "2024/25", "прошлый"])
async def test_bad_year_is_bad_request_without_diary_call(api, fake_diary, year):
    response = await api.get("/v1/final-marks", params={"year": year})

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert fake_diary.calls == []


async def test_mark_detail(api, fake_diary):
    from diarysdk.models.marks import MarkDetail

    fake_diary.answers["mark"] = MarkDetail(id=10001, value="9")

    response = await api.get("/v1/marks/10001")

    assert response.status_code == 200
    assert response.json()["value"] == "9"
    assert response.json()["class_results"] is None
    assert fake_diary.args["mark"][1] == 10001


async def test_unknown_mark_is_not_found(api, fake_diary):
    from diarysdk.errors import NotFound

    fake_diary.answers["mark"] = NotFound()

    response = await api.get("/v1/marks/999")

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


@pytest.mark.parametrize("mark_id", ["abc", "-1", "0"])
async def test_bad_mark_id_is_bad_request(api, fake_diary, mark_id):
    response = await api.get(f"/v1/marks/{mark_id}")

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert fake_diary.calls == []


async def test_marks_end_only_in_past_year_starts_that_school_year(api, fake_diary):
    fake_diary.answers["marks"] = []

    response = await api.get("/v1/marks", params={"to": "2026-05-31"})

    assert response.status_code == 200
    assert fake_diary.args["marks"][1:] == (date(2025, 9, 1), date(2026, 5, 31))
