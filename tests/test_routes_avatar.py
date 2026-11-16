from diarysdk.errors import NoAvatar
from diarysdk.models.avatar import Avatar


async def test_avatar_is_returned_as_is(api, fake_diary):
    fake_diary.answers["avatar"] = Avatar(content=b"\x89PNG-bytes", content_type="image/png")

    response = await api.get("/v1/me/avatar")

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/png"
    assert response.content == b"\x89PNG-bytes"
    assert response.headers["Cache-Control"] == "no-store"


async def test_no_avatar(api, fake_diary):
    fake_diary.answers["avatar"] = NoAvatar()

    response = await api.get("/v1/me/avatar")

    assert response.status_code == 404
    assert response.json()["error"] == "no_avatar"
