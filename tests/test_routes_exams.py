from diarysdk.models.exams import Exam


async def test_exams(api, fake_diary):
    fake_diary.answers["exams"] = [Exam(kind="ОГЭ", subject="Математика")]

    response = await api.get("/v1/exams")

    assert response.status_code == 200
    assert response.json() == [
        {"kind": "ОГЭ", "subject": "Математика", "date": None, "score": None, "mark": None}
    ]
