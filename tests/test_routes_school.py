from diarysdk.errors import NotFound
from diarysdk.models.school import School


async def test_school(api, fake_diary):
    fake_diary.answers["school"] = School(name="Гимназия")

    response = await api.get("/v1/school")

    assert response.status_code == 200
    assert response.json()["name"] == "Гимназия"
    assert response.json()["branches"] == []


async def test_school_not_found(api, fake_diary):
    fake_diary.answers["school"] = NotFound()

    response = await api.get("/v1/school")

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
