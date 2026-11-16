from datetime import UTC, date, datetime

import pytest

from diarysdk._api import raw
from diarysdk._hosts import Hosts
from diarysdk._port import StudentContext
from diarysdk.errors import UpstreamFormat
from tests.fakes import FakeTransport, fixture

TOKEN = "header.payload.signature"
HOSTS = Hosts(
    dnevnik="https://dnevnik.test", school_api="https://school-api.test", school="https://s.test"
)
STUDENT = StudentContext(
    student_id=33,
    person_guid="guid-1",
    profile_id=11,
    class_unit_id=22,
    school_id=44,
    expires_at=datetime(2026, 11, 1, tzinfo=UTC),
)


@pytest.fixture
def fake():
    return FakeTransport()


async def test_avatar_list_with_site_header_headers(fake):
    fake.add("/api/avatarmanagement/v1/guid-1", [{"id": 5, "url": "-", "default": True}])

    result = await raw.avatars(fake, HOSTS, TOKEN, "guid-1")

    assert result == [{"id": 5, "url": "-", "default": True}]
    assert fake.sent[0].header("authorization") == f"Bearer {TOKEN}"
    assert fake.sent[0].header("x-mes-subsystem") == "headerweb"
    assert fake.sent[0].header("x-mes-hostid") == "2"
    assert fake.sent[0].call == "avatar.list"


async def test_avatar_image_by_image_id(fake):
    fake.add("/avatars/guid-1", b"\x89PNG", content_type="image/png")

    response = await raw.avatar(fake, HOSTS, TOKEN, "guid-1", 5)

    assert response.body == b"\x89PNG"
    assert response.content_type == "image/png"
    assert fake.sent[0].params == {"image_id": "5"}
    assert fake.sent[0].header("authorization") == f"Bearer {TOKEN}"
    assert fake.sent[0].call == "avatar"


async def test_govexams_with_role_cookie(fake):
    fake.add("/portfolio/app/persons/guid-1/govexams/list/", {"data": []})

    result = await raw.govexams(fake, HOSTS, TOKEN, "guid-1")

    assert result == {"data": []}
    assert fake.sent[0].url == "https://dnevnik.test/portfolio/app/persons/guid-1/govexams/list/"
    assert fake.sent[0].header("cookie") == "aupd_current_role=4:1"
    assert fake.sent[0].header("authorization") == f"Bearer {TOKEN}"


async def test_not_json_where_json_expected_is_format_error(fake):
    fake.add("/portfolio/app/persons/guid-1/govexams/list/", "<html>", content_type="text/html")

    with pytest.raises(UpstreamFormat):
        await raw.govexams(fake, HOSTS, TOKEN, "guid-1")


async def test_mobile_homeworks(fake):
    fake.add("/family/mobile/v1/homeworks", {"payload": []})

    await raw.homeworks(fake, HOSTS, TOKEN, STUDENT, date(2026, 10, 24), date(2026, 10, 31))

    [sent] = fake.sent
    assert sent.url == "https://school-api.test/family/mobile/v1/homeworks"
    assert sent.params == {"from": "2026-10-24", "to": "2026-10-31", "student_id": "33"}
    assert sent.header("auth-token") == TOKEN
    assert sent.header("x-mes-subsystem") == "familymp"
    assert sent.header("client-type") == "diary-mobile"
    assert sent.header("profile-id") == "11"
    assert sent.call == "homework"


async def test_lesson_schedule_item(fake):
    fake.add("/family/mobile/v1/lesson_schedule_items/20001", {"id": 20001})

    data = await raw.lesson_schedule_item(fake, HOSTS, TOKEN, STUDENT, 20001)

    [sent] = fake.sent
    assert data == {"id": 20001}
    assert sent.url == "https://school-api.test/family/mobile/v1/lesson_schedule_items/20001"
    assert sent.params == {"student_id": "33", "type": "PLAN"}
    assert sent.header("x-mes-subsystem") == "familymp"
    assert sent.header("profile-id") == "11"
    assert sent.call == "lesson"


async def test_rating_class_for_subject(fake):
    fake.add("/api/ej/rating/v1/rank/class", [])

    data = await raw.rating_class_subject(fake, HOSTS, TOKEN, STUDENT, 77, date(2026, 10, 24))

    [sent] = fake.sent
    assert data == []
    assert sent.url == "https://dnevnik.test/api/ej/rating/v1/rank/class"
    assert sent.params == {
        "personId": "guid-1",
        "classUnitId": "22",
        "date": "2026-10-24",
        "subjectId": "77",
    }
    assert sent.header("auth-token") == TOKEN
    assert sent.header("x-mes-subsystem") == "familymp"
    assert sent.header("profile-id") == "11"
    assert sent.call == "rating.class.subject"


@pytest.mark.parametrize(
    ("done", "method", "call"),
    [(True, "POST", "homework.done"), (False, "DELETE", "homework.undone")],
)
async def test_homework_done_like_official_app(fake, done, method, call):
    fake.add("/family/mobile/v1/homeworks/555/done", b"")

    response = await raw.homework_done(fake, HOSTS, TOKEN, STUDENT, 555, done)

    [sent] = fake.sent
    assert response.status == 200
    assert sent.method == method
    assert sent.url == "https://school-api.test/family/mobile/v1/homeworks/555/done"
    assert sent.params == {}
    assert sent.json is None
    assert sent.header("auth-token") == TOKEN
    assert sent.header("x-mes-subsystem") == "familymp"
    assert sent.header("client-type") == "diary-mobile"
    assert sent.header("profile-id") == "11"
    assert sent.call == call


async def test_mark_info_with_own_student_id_and_mobile_headers(fake):
    fake.add("/family/mobile/v1/marks/10001", fixture("mark_info.json"))

    info = await raw.mark_info(fake, HOSTS, TOKEN, STUDENT, 10001)

    [sent] = fake.sent
    assert sent.method == "GET"
    assert sent.url == "https://school-api.test/family/mobile/v1/marks/10001"
    # student_id — только из контекста ученика: другого значения запрос не несёт.
    assert sent.params == {"student_id": "33"}
    assert sent.header("auth-token") == TOKEN
    assert sent.header("x-mes-subsystem") == "familymp"
    assert sent.header("client-type") == "diary-mobile"
    assert sent.header("profile-id") == "11"
    assert sent.call == "mark.info"
    assert info.id == 10001


def test_mark_info_fixture_passes_own_model():
    info = raw.MarkInfo.model_validate(fixture("mark_info.json"))

    assert info.class_results.total_students == 25
    assert info.teacher.last_name == "Учителева"


async def test_mark_info_keeps_unknown_fields(fake):
    data = {**fixture("mark_info.json"), "something_new": 1}
    fake.add("/family/mobile/v1/marks/10001", data)

    info = await raw.mark_info(fake, HOSTS, TOKEN, STUDENT, 10001)

    assert info.model_extra["something_new"] == 1


async def test_mark_info_of_wrong_shape_is_format_error(fake):
    fake.add("/family/mobile/v1/marks/10001", {"id": "не число", "class_results": 5})

    with pytest.raises(UpstreamFormat) as error:
        await raw.mark_info(fake, HOSTS, TOKEN, STUDENT, 10001)

    assert "не число" not in str(error.value)


async def test_mark_info_not_object_is_format_error(fake):
    fake.add("/family/mobile/v1/marks/10001", [])

    with pytest.raises(UpstreamFormat):
        await raw.mark_info(fake, HOSTS, TOKEN, STUDENT, 10001)


USER_SETTINGS_PATH = "/api/usersettings/v1"


async def test_user_settings_request(fake):
    fake.add(USER_SETTINGS_PATH, fixture("user_settings.json"))

    data = await raw.user_settings(fake, HOSTS, TOKEN, STUDENT)

    [ours] = fake.sent
    assert ours.url == "https://dnevnik.test/api/usersettings/v1"
    assert ours.params == {"name": "settings_group_v1", "subsystem_id": "1"}
    assert ours.header("x-mes-subsystem") == "familymp"
    assert ours.header("profile-id") == "11"
    assert ours.header("auth-token") == TOKEN
    assert ours.call == "user.settings"
    assert data == fixture("user_settings.json")


@pytest.mark.parametrize(
    ("body", "status"),
    [(b"", 200), (b"  \n", 200), ("null", 200), ("{}", 200), (b"", 404)],
    ids=["empty", "blank", "null", "empty_object", "not_found"],
)
async def test_user_settings_missing_group_is_none(fake, body, status):
    fake.add(USER_SETTINGS_PATH, body, status=status)

    assert await raw.user_settings(fake, HOSTS, TOKEN, STUDENT) is None


async def test_user_settings_not_object_is_format_error(fake):
    fake.add(USER_SETTINGS_PATH, [1])

    with pytest.raises(UpstreamFormat):
        await raw.user_settings(fake, HOSTS, TOKEN, STUDENT)


def test_user_settings_params_are_read_only():
    # Общий словарь запросов настроек: правка одного вызова испортила бы все.
    with pytest.raises(TypeError):
        raw.USER_SETTINGS_PARAMS["name"] = "other"
