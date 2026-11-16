from datetime import date

from diarysdk._mapping.me import me
from diarysdk.errors import MultipleChildren, UpstreamFormat
from tests.fakes import STUDENT


def sample_me():
    from diarysdk._wire.web import WebFamilyProfile
    from tests.fakes import fixture

    return me(
        WebFamilyProfile.model_validate(fixture("profile.json")),
        STUDENT.expires_at,
        date(2026, 10, 24),
    )


async def test_me_returns_contract_shape(api, fake_diary):
    fake_diary.answers["me"] = sample_me()

    response = await api.get("/v1/me")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "person",
        "school",
        "class",
        "study_profile",
        "sections",
        "enrolled_on",
        "token",
    }
    assert body["class"] == {"id": 4001, "name": "10-Ф", "level": 10}
    assert response.headers["Cache-Control"] == "no-store"
    assert fake_diary.calls == ["student_context", "me"]


async def test_parent_with_two_children_gets_422(api, fake_diary):
    fake_diary.answers["student_context"] = MultipleChildren()

    response = await api.get("/v1/me")

    assert response.status_code == 422
    assert response.json()["error"] == "multiple_children"


async def test_profile_without_child_gets_upstream_format(api, fake_diary):
    fake_diary.answers["student_context"] = UpstreamFormat(problems=["children: пусто"])

    response = await api.get("/v1/me")

    assert response.status_code == 502
    assert response.json()["error"] == "upstream_format"
