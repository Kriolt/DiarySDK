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


async def test_work_program_route(api, fake_diary):
    fake_diary.answers["work_program"] = []

    response = await api.get("/v1/groups/5001/program")

    assert response.status_code == 200
    assert fake_diary.args["work_program"][1:] == (5001,)


async def test_subject_topics_route(api, fake_diary):
    fake_diary.answers["subject_topics"] = []

    response = await api.get("/v1/subjects/101/topics")

    assert response.status_code == 200
    assert fake_diary.args["subject_topics"][1:] == (101,)


async def test_control_works_route_defaults_to_school_year(api, fake_diary, today):
    from datetime import date

    fake_diary.answers["control_works"] = []

    response = await api.get("/v1/control-works")

    assert response.status_code == 200
    assert fake_diary.args["control_works"][1:] == (date(2026, 9, 1), date(2027, 8, 31))


async def test_final_marks_file_route(api, fake_diary):
    from diarysdk.models import DiaryFile

    fake_diary.answers["final_marks_file"] = DiaryFile(b"%PDF-1", "application/pdf", "f.pdf")

    response = await api.get(
        "/v1/final-marks/file", params={"year": 2025, "orientation": "landscape"}
    )

    assert response.status_code == 200
    assert response.content == b"%PDF-1"
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="f.pdf"' in response.headers["content-disposition"]
    assert fake_diary.args["final_marks_file"][1:] == (2025, "landscape")


async def test_final_marks_file_bad_orientation(api, fake_diary):
    response = await api.get("/v1/final-marks/file", params={"orientation": "sideways"})

    assert response.status_code == 400
    assert "final_marks_file" not in fake_diary.calls


async def test_certificates_route(api, fake_diary):
    from diarysdk.models import Certificate

    fake_diary.answers["certificates"] = [Certificate(id=1, status="Сформирована")]

    response = await api.get("/v1/certificates")

    assert (response.status_code, response.json()[0]["status"]) == (200, "Сформирована")
