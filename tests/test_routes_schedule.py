from datetime import date

import pytest


async def test_schedule_defaults_to_current_week(api, fake_diary):
    fake_diary.answers["schedule"] = []

    response = await api.get("/v1/schedule")

    assert response.status_code == 200
    # 24.10.2026 — суббота: неделя с понедельника 19-го по воскресенье 25-е.
    assert fake_diary.args["schedule"][1:] == (date(2026, 10, 19), date(2026, 10, 25))


async def test_schedule_from_next_monday_gets_that_week(api, fake_diary):
    fake_diary.answers["schedule"] = []

    await api.get("/v1/schedule", params={"from": "2026-10-26"})

    assert fake_diary.args["schedule"][1:] == (date(2026, 10, 26), date(2026, 11, 1))


@pytest.mark.parametrize(
    "params",
    [{"from": "2026-10-01", "to": "2026-11-01"}, {"from": "2026-10-20", "to": "2026-10-19"}],
)
async def test_bad_schedule_period(api, fake_diary, params):
    response = await api.get("/v1/schedule", params=params)

    assert response.status_code == 400
    assert fake_diary.calls == []
