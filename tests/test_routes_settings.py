import pytest

from diarysdk.errors import SettingNotSet, SettingsMissing, SettingUnrestorable, UpstreamError
from diarysdk.models.settings import Settings, SettingsTheme


async def test_settings(api, fake_diary):
    fake_diary.answers["settings"] = Settings(
        goal=False, theme=SettingsTheme(type="dark"), schedule_type="compact"
    )

    response = await api.get("/v1/settings")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "goal": False,
        "theme": {"type": "dark", "is_automatic": None, "color_pattern": None},
        "schedule_type": "compact",
        "estimation_type": None,
    }


async def test_diary_error_is_upstream_error(api, fake_diary):
    fake_diary.answers["settings"] = UpstreamError(upstream_status=503)

    response = await api.get("/v1/settings")

    assert response.status_code == 502
    assert response.json()["upstream_status"] == 503


async def test_patch_answers_no_content_and_passes_only_given_fields(api, fake_diary):
    fake_diary.answers["update_settings"] = None

    response = await api.patch("/v1/settings", json={"goal": False, "theme": {"type": "dark"}})

    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["cache-control"] == "no-store"
    update = fake_diary.args["update_settings"][1]
    assert update.changes() == {"goal": False, "theme.type": "dark"}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"theme": {}},
        {"goal": None},
        {"theme": None},
        {"theme": {"type": None}},
        {"estimation_type": "five"},
        {"goal": True, "extra": 1},
        {"theme": {"type": "blue"}},
        {"schedule_type": "wide"},
        {"goal": "yes"},
    ],
)
async def test_bad_body_is_bad_request_without_diary_call(api, fake_diary, body):
    response = await api.patch("/v1/settings", json=body)

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert fake_diary.calls == []


async def test_no_body_is_bad_request(api, fake_diary):
    response = await api.patch("/v1/settings")

    assert response.status_code == 400
    assert fake_diary.calls == []


async def test_missing_group_is_conflict(api, fake_diary):
    fake_diary.answers["update_settings"] = SettingsMissing()

    response = await api.patch("/v1/settings", json={"goal": True})

    assert response.status_code == 409
    assert response.json()["error"] == "settings_missing"


async def test_unset_field_is_conflict_naming_the_field(api, fake_diary):
    fake_diary.answers["update_settings"] = SettingNotSet(field="theme.type")

    response = await api.patch("/v1/settings", json={"theme": {"type": "dark"}})

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "setting_unset"
    assert "theme.type" in body["message"]


async def test_unrestorable_field_is_conflict_naming_the_field(api, fake_diary):
    fake_diary.answers["update_settings"] = SettingUnrestorable(field="theme.color_pattern")

    response = await api.patch("/v1/settings", json={"theme": {"color_pattern": "pink"}})

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "setting_unrestorable"
    assert "theme.color_pattern" in body["message"]


async def test_upstream_refusal_is_bad_gateway_with_status(api, fake_diary):
    fake_diary.answers["update_settings"] = UpstreamError(upstream_status=403)

    response = await api.patch("/v1/settings", json={"goal": True})

    assert response.status_code == 502
    assert response.json()["error"] == "upstream_error"
    assert response.json()["upstream_status"] == 403
