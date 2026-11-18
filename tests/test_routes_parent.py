"""Маршруты родителя и child_id в маршрутах ученика (ядро с подставным шлюзом)."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from diarysdk._port import ParentContext
from diarysdk._wire.web import WebFamilyProfile
from diarysdk.models import Child, ParentMe, SchoolBrief, TokenExpiry
from diarysdk.server.app import create_app
from diarysdk.server.keys import hash_key
from tests.conftest import API_KEY, AUTH_HEADERS
from tests.fakes import core_diary

PARENT = ParentContext(
    profile_id=7001,
    person_guid="00000000-0000-4000-8000-000000000201",
    expires_at=datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
    profile=WebFamilyProfile(),
)
CHILDREN = [Child(id=9001, school=SchoolBrief()), Child(id=9002, school=SchoolBrief())]


@pytest.fixture
def keys_file(tmp_path):
    path = tmp_path / "api-keys"
    path.write_text(f"tests {hash_key(API_KEY)} write_profile\n")
    return path


@pytest.fixture
def fake_diary(fake_diary):
    fake_diary.answers["parent_context"] = PARENT
    return fake_diary


@pytest.fixture
async def plain(tmp_path, fake_diary, today):
    """Ключ без разрешений на запись."""
    from diarysdk.server.config import Settings

    path = tmp_path / "plain-keys"
    path.write_text(f"tests {hash_key(API_KEY)}\n")
    app = create_app(Settings(keys_file=path, version="x"), diary=core_diary(fake_diary))
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers=AUTH_HEADERS
    ) as c:
        yield c


async def test_children(api, fake_diary):
    fake_diary.answers["parent_children"] = CHILDREN

    response = await api.get("/v1/parent/children")

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == [9001, 9002]


async def test_me(api, fake_diary):
    fake_diary.answers["parent_me"] = ParentMe(
        first_name="Пётр", type="parent", token=TokenExpiry(expires_at=PARENT.expires_at)
    )

    response = await api.get("/v1/parent/me")

    assert (response.status_code, response.json()["type"]) == (200, "parent")


async def test_student_route_with_child_id_selects_child(api, fake_diary):
    fake_diary.answers["marks"] = []

    response = await api.get("/v1/marks", params={"child_id": 9002})

    assert response.status_code == 200
    assert fake_diary.args["student_context"][1:] == (9002,)


async def test_student_route_without_child_id_is_as_before(api, fake_diary):
    fake_diary.answers["marks"] = []

    await api.get("/v1/marks")

    assert fake_diary.args["student_context"][1:] == (None,)


@pytest.mark.parametrize("child_id", ["0", "-1", "x"])
async def test_bad_child_id_is_bad_request(api, fake_diary, child_id):
    response = await api.get("/v1/marks", params={"child_id": child_id})

    assert response.status_code == 400
    assert fake_diary.calls == []


async def test_update_settings_is_no_content(api, fake_diary):
    fake_diary.answers["parent_update_settings"] = None

    response = await api.patch("/v1/parent/settings", json={"goal": True})

    assert response.status_code == 204
    assert fake_diary.args["parent_update_settings"][1].goal is True


async def test_contact_without_write_profile_is_forbidden(plain, fake_diary):
    response = await plain.put("/v1/parent/identity/contacts/2", json={"value": "new@example.test"})

    assert response.status_code == 403
    assert response.json()["error"] == "forbidden_scope"
    assert fake_diary.calls == []


async def test_contact_with_write_profile(api, fake_diary):
    fake_diary.answers["parent_update_contact"] = None

    response = await api.put("/v1/parent/identity/contacts/2", json={"value": "new@example.test"})

    assert response.status_code == 204
    assert fake_diary.args["parent_update_contact"][1:] == (2, "new@example.test")
