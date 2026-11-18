"""Маршруты новых чтений журнала: учителя школы и задолженности."""

from diarysdk.models import AcademicDebt, SchoolTeacher, Subject


async def test_school_teachers_route(api, fake_diary):
    fake_diary.answers["school_teachers"] = [SchoolTeacher(id=1, name="Учитель")]

    response = await api.get("/v1/school/teachers", params={"name": "Уч"})

    assert response.status_code == 200
    assert response.json()[0]["name"] == "Учитель"
    assert fake_diary.args["school_teachers"][1:] == ("Уч",)


async def test_academic_debts_route_defaults_to_current_year(api, fake_diary, today):
    fake_diary.answers["academic_debts"] = [
        AcademicDebt(subject=Subject(id=1, name="Алгебра"), attested=False)
    ]

    response = await api.get("/v1/academic-debts")

    assert response.status_code == 200
    assert response.json()[0]["attested"] is False
    assert fake_diary.args["academic_debts"][1:] == (2026,)


async def test_academic_debts_future_year_is_bad_request(api, fake_diary):
    response = await api.get("/v1/academic-debts", params={"year": 2030})

    assert response.status_code == 400
    assert "academic_debts" not in fake_diary.calls
