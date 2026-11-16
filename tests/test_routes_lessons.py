import pytest

from diarysdk.errors import NotFound
from diarysdk.models.lessons import Lesson


async def test_lesson_by_id(api, fake_diary):
    fake_diary.answers["lesson"] = Lesson(id=20001)

    response = await api.get("/v1/lessons/20001")

    assert response.status_code == 200
    assert response.json()["id"] == 20001
    assert fake_diary.args["lesson"][1] == 20001


@pytest.mark.parametrize("lesson_id", ["abc", "-1", "0"])
async def test_lesson_id_must_be_a_positive_number(api, fake_diary, lesson_id):
    response = await api.get(f"/v1/lessons/{lesson_id}")

    assert response.status_code == 400
    assert fake_diary.calls == []


async def test_unknown_lesson_is_not_found(api, fake_diary):
    fake_diary.answers["lesson"] = NotFound()

    response = await api.get("/v1/lessons/1")

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
