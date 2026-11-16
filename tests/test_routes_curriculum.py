from diarysdk.errors import NotFound
from diarysdk.models.curriculum import Curriculum


async def test_curriculum(api, fake_diary):
    fake_diary.answers["curriculum"] = Curriculum(title="УП", hours=34)

    response = await api.get("/v1/curriculum")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "УП"
    assert body["sections"] == []
    assert body["weeks"] == []


async def test_no_curriculum_is_not_found(api, fake_diary):
    fake_diary.answers["curriculum"] = NotFound()

    response = await api.get("/v1/curriculum")

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
