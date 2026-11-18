"""Parent ядра на подставном дневнике: свои данные родителя и выбор ребёнка."""

import json

import pytest

from diarysdk import Parent, Student, errors
from tests.fakes import fixture
from tests.test_client import DiaryServer, now, token  # noqa: F401 - фикстуры
from tests.test_golden import SETTINGS_UPDATE

PARENT_GUID = "00000000-0000-4000-8000-000000000201"
PARENT_SNILS = "000-000-000 01"


def parent_profile(children: int = 2, *, own_rep: bool = True) -> dict:
    data = fixture("profile.json")
    data["profile"].update(
        type="parent",
        first_name="Пётр",
        last_name="Тестов",
        snils=PARENT_SNILS,
        email="parent@example.test",
    )
    first = data["children"][0]
    reps = [{"person_id": PARENT_GUID, "snils": PARENT_SNILS, "type": "Отец"}] if own_rep else []
    first["representatives"] = reps
    second = {**first, "id": 9002, "class_unit_id": 4002, "class_name": "7-Б"}
    data["children"] = [first, second][:children]
    return data


@pytest.fixture
def server():
    server = DiaryServer()
    server.fake.add("/api/family/web/v1/profile", parent_profile())
    server.fake.add(f"/api/persondata/v1/persons/{PARENT_GUID}", fixture("person_data.json"))
    server.fake.add(f"/api/avatarmanagement/v1/{PARENT_GUID}", [{"id": 5, "default": True}])
    server.fake.add(f"/avatars/{PARENT_GUID}", b"\x89PNG-parent", content_type="image/png")
    return server


@pytest.fixture
async def parent(server, now, token):  # noqa: F811
    async with server.diary() as diary:
        yield diary.parent(token)


async def test_parent_is_created_without_requests(server, now, token):  # noqa: F811
    async with server.diary() as diary:
        parent = diary.parent(token)
        assert isinstance(parent, Parent)
        assert isinstance(parent.student(9002), Student)
    assert server.requests == []


async def test_children_lists_accessible_students(parent):
    children = await parent.children()

    assert [(c.id, c.class_name) for c in children] == [(9001, "10-Ф"), (9002, "7-Б")]
    assert children[1].school.id is not None


async def test_student_by_child_id_reads_that_child(parent, server):
    await parent.student(9002).marks()

    marks = [r for r in server.requests if r.url.path == "/family/mobile/v1/marks"]
    assert marks[-1].url.params["student_id"] == "9002"


async def test_me_through_parent_is_the_selected_child(parent):
    me = await parent.student(9002).me()

    assert me.class_.id == 4002


async def test_unknown_child_is_not_found(parent):
    with pytest.raises(errors.NotFound):
        await parent.student(999).marks()


async def test_parent_without_children(server, parent):
    server.fake.add("/api/family/web/v1/profile", parent_profile(children=0))

    assert await parent.children() == []
    with pytest.raises(errors.NotFound):
        await parent.student(5).marks()


async def test_student_token_is_not_for_parent(server, parent):
    server.fake.add("/api/family/web/v1/profile", fixture("profile.json"))

    with pytest.raises(errors.NotForRole) as error:
        await parent.me()
    assert error.value.role == "student"


async def test_me_is_parent_profile(parent):
    me = await parent.me()

    assert (me.first_name, me.last_name, me.type) == ("Пётр", "Тестов", "parent")
    assert me.email == "parent@example.test"
    assert me.token.expires_at is not None
    assert "snils" not in me.model_dump()


async def test_identity_reads_parent_card(parent, server):
    card = await parent.identity()

    assert server.count("GET", f"/api/persondata/v1/persons/{PARENT_GUID}") == 1
    assert card.person.first_name == "Пётр"
    assert card.representatives == []


async def test_identity_without_own_representative_has_no_card(server, parent):
    server.fake.add("/api/family/web/v1/profile", parent_profile(own_rep=False))

    card = await parent.identity()

    assert card.person.documents == []
    assert not any("/persondata/" in r.url.path for r in server.requests)


async def test_avatar_is_parent_own(parent):
    avatar = await parent.avatar()

    assert avatar.content == b"\x89PNG-parent"


async def test_settings_use_parent_profile(parent, server):
    await parent.settings()

    request = next(r for r in server.requests if r.url.path == "/api/usersettings/v1")
    assert request.headers["profile-id"] == "7001"


async def test_update_settings_writes_parent_profile(parent, server):
    await parent.update_settings(SETTINGS_UPDATE)

    put = next(r for r in server.requests if r.method == "PUT")
    assert put.url.path == "/api/usersettings/v1"
    assert put.headers["profile-id"] == "7001"


async def test_update_contact_checks_email_before_request(parent, server):
    with pytest.raises(errors.BadRequest):
        await parent.update_contact(1, "не почта")
    assert server.requests == []


def test_repr_hides_token(token):  # noqa: F811
    from diarysdk import Diary

    text = repr(Diary().parent(token))
    assert token.value not in text and "Parent(" in text
    assert json.dumps(text)


async def test_parent_guid_comes_from_msh_claim(server, now):  # noqa: F811
    from diarysdk import Token
    from tests.fakes import STUDENT
    from tests.tokens import make_token

    server.fake.add("/api/family/web/v1/profile", parent_profile(own_rep=False))
    async with server.diary() as diary:
        parent = diary.parent(Token(make_token(STUDENT.expires_at, msh=PARENT_GUID)))
        await parent.identity()

    assert server.count("GET", f"/api/persondata/v1/persons/{PARENT_GUID}") == 1
