from datetime import date

import pytest

from diarysdk.errors import NotFound


async def test_homework_defaults_to_week_ahead_by_due_date(api, fake_diary):
    fake_diary.answers["homework"] = []

    response = await api.get("/v1/homework")

    assert response.status_code == 200
    assert fake_diary.args["homework"][1:] == (date(2026, 10, 24), date(2026, 10, 31))


async def test_homework_longer_than_month_is_bad_request(api, fake_diary):
    response = await api.get("/v1/homework", params={"from": "2026-10-01", "to": "2026-11-15"})

    assert response.status_code == 400
    assert fake_diary.calls == []


@pytest.mark.parametrize(("method", "done"), [("POST", True), ("DELETE", False)])
async def test_homework_done_answers_no_content(api, fake_diary, method, done):
    fake_diary.answers["set_homework_done"] = None

    response = await api.request(method, "/v1/homework/555/done")

    assert response.status_code == 204
    assert response.content == b""
    assert fake_diary.args["set_homework_done"][1:] == (555, done)


@pytest.mark.parametrize("homework_id", ["0", "-1", "abc"])
async def test_bad_homework_id_is_bad_request(api, fake_diary, homework_id):
    response = await api.post(f"/v1/homework/{homework_id}/done")

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert fake_diary.calls == []


async def test_done_for_missing_homework_is_not_found(api, fake_diary):
    fake_diary.answers["set_homework_done"] = NotFound()

    response = await api.delete("/v1/homework/555/done")

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
    assert fake_diary.args["set_homework_done"][1:] == (555, False)
