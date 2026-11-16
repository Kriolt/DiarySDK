"""Запись настроек: прочитать группу, поменять поля из запроса, записать целиком."""

import copy

import pytest

from diarysdk._gateway import DiaryGateway
from diarysdk._port import Ctx
from diarysdk.errors import (
    NotFound,
    SettingNotSet,
    SettingsMissing,
    SettingUnrestorable,
    TokenInvalid,
    UpstreamError,
)
from diarysdk.models.settings import SettingsThemeUpdate, SettingsUpdate
from tests.fakes import CTX, HOSTS, STUDENT, FakeTransport, core_diary, fixture
from tests.tokens import valid_token

PATH = "/api/usersettings/v1"


@pytest.fixture
def fake():
    fake = FakeTransport()
    fake.add(f"GET {PATH}", fixture("user_settings.json"))
    fake.add(f"PUT {PATH}", b"")
    return fake


@pytest.fixture
def gateway(fake):
    return DiaryGateway(fake, HOSTS)


def puts(fake):
    return [s for s in fake.sent if s.method == "PUT"]


async def test_put_has_whole_object_with_unknown_fields_as_read(gateway, fake):
    update = SettingsUpdate(
        goal=True,
        theme=SettingsThemeUpdate(color_pattern="pink"),
        schedule_type="full",
    )

    assert await gateway.update_settings(CTX, update) is None

    [put] = puts(fake)
    expected = copy.deepcopy(fixture("user_settings.json"))
    expected["goal"] = True
    expected["theme"]["color_pattern"] = "pink"
    expected["schedule_type"] = "full"
    assert put.json == expected
    # extra_key и theme.future_field не потерялись, estimation_type не тронут.
    assert put.json["extra_key"] == {"nested": [1, 2]}
    assert put.json["theme"]["future_field"] == "x"
    assert put.json["estimation_type"] == "five"
    assert put.url == "https://dnevnik.test/api/usersettings/v1"
    assert put.params == {"name": "settings_group_v1", "subsystem_id": "1"}
    assert put.header("x-mes-subsystem") == "familymp"
    assert put.header("profile-id") == "7001"
    assert put.header("auth-token") == CTX.token
    assert put.call == "user.settings.put"


async def test_only_requested_fields_change(gateway, fake):
    await gateway.update_settings(CTX, SettingsUpdate(schedule_type="full"))

    [put] = puts(fake)
    expected = fixture("user_settings.json")
    expected["schedule_type"] = "full"
    assert put.json == expected


async def test_only_the_settings_group_is_touched(gateway, fake):
    await gateway.update_settings(CTX, SettingsUpdate(goal=True))

    assert {s.params["name"] for s in fake.sent} == {"settings_group_v1"}
    assert [s.method for s in fake.sent] == ["GET", "PUT"]


async def test_false_goal_is_a_set_value_and_can_be_written(gateway, fake):
    # В фикстуре goal=false: «ложь» — значение, а не «не задано».
    await gateway.update_settings(CTX, SettingsUpdate(goal=True))
    await gateway.update_settings(
        CTX, SettingsUpdate(theme=SettingsThemeUpdate(is_automatic=False))
    )

    assert puts(fake)[0].json["goal"] is True
    assert puts(fake)[1].json["theme"]["is_automatic"] is False


@pytest.mark.parametrize("falsy", [0, ""])
async def test_falsy_present_value_is_unrestorable_not_unset(gateway, fake, falsy):
    # Ложь — значение, а не «не задано»; но 0 и "" вне типа поля: вернуть нечем.
    data = fixture("user_settings.json")
    data["goal"] = falsy
    fake.add(f"GET {PATH}", data)

    with pytest.raises(SettingUnrestorable):
        await gateway.update_settings(CTX, SettingsUpdate(goal=True))

    assert puts(fake) == []


@pytest.mark.parametrize(
    ("body", "status"),
    [(b"", 200), ("null", 200), ("{}", 200), (b"", 404)],
    ids=["empty", "null", "empty_object", "not_found"],
)
async def test_missing_group_is_conflict_without_put(gateway, fake, body, status):
    fake.add(f"GET {PATH}", body, status=status)

    with pytest.raises(SettingsMissing):
        await gateway.update_settings(CTX, SettingsUpdate(goal=True))

    assert puts(fake) == []


@pytest.mark.parametrize(
    ("remove", "update", "field"),
    [
        ("goal", SettingsUpdate(goal=True), "goal"),
        ("schedule_type", SettingsUpdate(schedule_type="full"), "schedule_type"),
        ("theme", SettingsUpdate(theme=SettingsThemeUpdate(type="light")), "theme.type"),
        (
            "theme.type",
            SettingsUpdate(theme=SettingsThemeUpdate(type="light")),
            "theme.type",
        ),
        (
            "theme.is_automatic",
            SettingsUpdate(theme=SettingsThemeUpdate(is_automatic=True)),
            "theme.is_automatic",
        ),
    ],
)
@pytest.mark.parametrize("as_null", [False, True])
async def test_unset_field_is_conflict_naming_it_without_put(
    gateway, fake, remove, update, field, as_null
):
    data = fixture("user_settings.json")
    target = data
    *parents, last = remove.split(".")
    for name in parents:
        target = target[name]
    if as_null:
        target[last] = None
    else:
        del target[last]
    fake.add(f"GET {PATH}", data)

    with pytest.raises(SettingNotSet) as caught:
        await gateway.update_settings(CTX, update)

    assert caught.value.field == field
    assert puts(fake) == []


async def test_theme_null_or_not_an_object_is_unset(gateway, fake):
    data = fixture("user_settings.json")
    data["theme"] = None
    fake.add(f"GET {PATH}", data)

    with pytest.raises(SettingNotSet):
        await gateway.update_settings(CTX, SettingsUpdate(theme=SettingsThemeUpdate(type="dark")))


async def test_one_unset_field_blocks_the_whole_write(gateway, fake):
    data = fixture("user_settings.json")
    del data["schedule_type"]
    fake.add(f"GET {PATH}", data)

    with pytest.raises(SettingNotSet):
        await gateway.update_settings(CTX, SettingsUpdate(goal=True, schedule_type="full"))

    assert puts(fake) == []


@pytest.mark.parametrize(
    ("path", "current", "update", "field"),
    [
        (
            "theme.color_pattern",
            "blue",
            SettingsThemeUpdate(color_pattern="pink"),
            "theme.color_pattern",
        ),
        ("theme.type", "auto", SettingsThemeUpdate(type="dark"), "theme.type"),
        ("theme.is_automatic", "yes", SettingsThemeUpdate(is_automatic=True), "theme.is_automatic"),
        ("goal", "true", None, "goal"),
        ("schedule_type", "weekly", None, "schedule_type"),
    ],
)
async def test_current_value_outside_what_we_can_write_is_conflict_without_put(
    gateway, fake, path, current, update, field
):
    data = fixture("user_settings.json")
    target = data
    *parents, last = path.split(".")
    for name in parents:
        target = target[name]
    target[last] = current
    fake.add(f"GET {PATH}", data)
    if update is None:
        update = SettingsUpdate(**{path: False if path == "goal" else "full"})
    elif parents:
        update = SettingsUpdate(theme=update)

    with pytest.raises(SettingUnrestorable) as caught:
        await gateway.update_settings(CTX, update)

    assert caught.value.field == field
    assert puts(fake) == []


async def test_unrestorable_field_not_in_the_request_is_ignored(gateway, fake):
    data = fixture("user_settings.json")
    data["theme"]["color_pattern"] = "blue"
    fake.add(f"GET {PATH}", data)

    await gateway.update_settings(CTX, SettingsUpdate(goal=True))

    [put] = puts(fake)
    assert put.json["theme"]["color_pattern"] == "blue"


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_refusal_on_put_is_upstream_error_with_status(gateway, fake, status):
    fake.add(f"PUT {PATH}", b"", status=status)

    with pytest.raises(UpstreamError) as caught:
        await gateway.update_settings(CTX, SettingsUpdate(goal=True))

    assert caught.value.upstream_status == status


async def test_not_found_on_put_is_not_found(gateway, fake):
    fake.add(f"PUT {PATH}", b"", status=404)

    with pytest.raises(NotFound):
        await gateway.update_settings(CTX, SettingsUpdate(goal=True))


async def test_success_false_on_put_is_upstream_error(gateway, fake):
    fake.add(f"PUT {PATH}", {"success": False})

    with pytest.raises(UpstreamError):
        await gateway.update_settings(CTX, SettingsUpdate(goal=True))


async def test_403_on_put_keeps_token_context_in_cache(gateway, fake):
    fake.add("/api/family/web/v1/profile", fixture("profile.json"))
    fake.add(f"PUT {PATH}", b"", status=403)
    diary = core_diary(gateway)
    token = valid_token()

    for _ in range(2):
        with pytest.raises(UpstreamError) as caught:
            await diary.student(token).update_settings(SettingsUpdate(goal=True))
        assert caught.value.upstream_status == 403

    profiles = [s for s in fake.sent if s.url.endswith("/api/family/web/v1/profile")]
    assert len(profiles) == 1


async def test_403_on_read_step_still_evicts_context(gateway, fake):
    fake.add("/api/family/web/v1/profile", fixture("profile.json"))
    fake.add(f"GET {PATH}", b"", status=403)
    diary = core_diary(gateway)

    for _ in range(2):
        with pytest.raises(TokenInvalid):
            await diary.student(valid_token()).update_settings(SettingsUpdate(goal=True))

    profiles = [s for s in fake.sent if s.url.endswith("/api/family/web/v1/profile")]
    assert len(profiles) == 2


def test_student_fixture_is_the_one_in_ctx():
    assert Ctx(token=CTX.token, student=STUDENT) == CTX
