from datetime import date

import pytest

from diarysdk.models.rating import Rating


async def test_rating_defaults_to_today(api, fake_diary, today):
    fake_diary.answers["rating"] = Rating.disabled()

    response = await api.get("/v1/rating")

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert fake_diary.args["rating"][1] == today


async def test_rating_on_given_date(api, fake_diary):
    fake_diary.answers["rating"] = Rating.disabled()

    await api.get("/v1/rating", params={"date": "2026-10-20"})

    assert fake_diary.args["rating"][1] == date(2026, 10, 20)


async def test_bad_date_is_bad_request(api, fake_diary):
    response = await api.get("/v1/rating", params={"date": "2026-13-01"})

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert "rating" not in fake_diary.calls


async def test_rating_subjects_defaults_to_today(api, fake_diary, today):
    fake_diary.answers["rating_subjects"] = []

    response = await api.get("/v1/rating/subjects")

    assert response.status_code == 200
    assert response.json() == []
    assert fake_diary.args["rating_subjects"][1] == today


async def test_rating_history_from_first_of_september_to_today(api, fake_diary):
    fake_diary.answers["rating_history"] = []

    response = await api.get("/v1/rating/history")

    assert response.status_code == 200
    assert fake_diary.args["rating_history"][1:] == (date(2026, 9, 1), date(2026, 10, 24))


async def test_rating_history_start_after_end_is_bad_request(api, fake_diary):
    response = await api.get(
        "/v1/rating/history", params={"from": "2026-10-10", "to": "2026-10-01"}
    )

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"


async def test_rating_for_one_subject(api, fake_diary, today):
    fake_diary.answers["rating"] = Rating.disabled()

    response = await api.get("/v1/rating", params={"subject": "77"})

    assert response.status_code == 200
    assert fake_diary.args["rating"][1:] == (today, 77)


async def test_rating_without_subject_is_whole_class(api, fake_diary, today):
    fake_diary.answers["rating"] = Rating.disabled()

    await api.get("/v1/rating")

    assert fake_diary.args["rating"][1:] == (today, None)


@pytest.mark.parametrize("subject", ["0", "-5", "алгебра"])
async def test_bad_subject_is_bad_request(api, fake_diary, subject):
    response = await api.get("/v1/rating", params={"subject": subject})

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert "rating" not in fake_diary.calls


async def test_rating_history_end_only_in_past_year_starts_that_school_year(api, fake_diary):
    fake_diary.answers["rating_history"] = []

    response = await api.get("/v1/rating/history", params={"to": "2026-05-31"})

    assert response.status_code == 200
    assert fake_diary.args["rating_history"][1:] == (date(2025, 9, 1), date(2026, 5, 31))
