import httpx
import pytest

from diarysdk import (
    SettingError,
    SettingNotSet,
    SettingsMissing,
    SettingUnrestorable,
    UpstreamError,
    UpstreamTimeout,
    WriteUncertain,
)
from diarysdk.models.settings import SettingsThemeUpdate, SettingsUpdate
from diarysdk.remote._core import update_settings
from tests.remote.helpers import remote_diary
from tests.tokens import valid_token

UPDATE = SettingsUpdate(goal=False, theme=SettingsThemeUpdate(type="dark"))
UPSTREAM_403 = {"error": "upstream_error", "message": "m", "upstream_status": 403}
# Так сервис помечает WriteUncertain: исход записи неизвестен.
UNCERTAIN = {"uncertain": True}


class Handler:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def async_client(handler):
    return remote_diary("http://t", "k", transport=httpx.MockTransport(handler))


def test_request_has_only_given_fields_as_patch():
    request = update_settings(UPDATE)

    assert (request.method, request.path) == ("PATCH", "/v1/settings")
    assert request.body == {"goal": False, "theme": {"type": "dark"}}
    assert request.uncertain
    assert "dark" not in repr(request)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (SettingsMissing(), "settings_missing"),
        (SettingNotSet(field="goal"), "setting_unset"),
        (SettingUnrestorable(field="goal"), "setting_unrestorable"),
    ],
)
async def test_409_is_setting_error(asgi_client, fake_diary, error, code):
    fake_diary.answers["update_settings"] = error

    with pytest.raises(SettingError) as caught:
        await asgi_client.student(valid_token()).update_settings(UPDATE)

    assert type(caught.value) is type(error)
    assert (caught.value.status, caught.value.code) == (409, code)
    if code != "settings_missing":
        assert "goal" in caught.value.message


async def test_real_app_passes_only_given_fields_to_diary(asgi_client, fake_diary):
    fake_diary.answers["update_settings"] = None

    assert await asgi_client.student(valid_token()).update_settings(UPDATE) is None

    assert fake_diary.args["update_settings"][1].changes() == {"goal": False, "theme.type": "dark"}


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(502, json={**UPSTREAM_403, **UNCERTAIN}),
        httpx.Response(504, json={"error": "upstream_timeout", "message": "m", **UNCERTAIN}),
        httpx.Response(502, text="<html>Bad Gateway</html>"),
        httpx.ConnectError("boom"),
        httpx.ReadTimeout("slow"),
    ],
    ids=["502", "504", "proxy-502", "connect", "timeout"],
)
async def test_async_write_is_uncertain_and_not_retried(answer):
    handler = Handler(answer)
    async with async_client(handler) as api:
        with pytest.raises(WriteUncertain):
            await api.student(valid_token()).update_settings(UPDATE)
    assert len(handler.calls) == 1


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (502, UPSTREAM_403, UpstreamError),
        (504, {"error": "upstream_timeout", "message": "m"}, UpstreamTimeout),
    ],
)
async def test_definite_failure_without_uncertain_mark_is_not_write_uncertain(
    status, body, expected
):
    handler = Handler(httpx.Response(status, json=body))
    async with async_client(handler) as api:
        with pytest.raises(expected) as caught:
            await api.student(valid_token()).update_settings(UPDATE)
    assert type(caught.value) is expected
    assert len(handler.calls) == 1


async def test_uncertain_write_exposes_upstream_status_to_tell_refusal_from_unknown():
    refused = Handler(httpx.Response(502, json={**UPSTREAM_403, **UNCERTAIN}))
    async with async_client(refused) as api:
        with pytest.raises(WriteUncertain) as caught:
            await api.student(valid_token()).update_settings(UPDATE)
    assert (caught.value.status, caught.value.upstream_status) == (502, 403)

    unknown = Handler(
        httpx.Response(504, json={"error": "upstream_timeout", "message": "m", **UNCERTAIN})
    )
    async with async_client(unknown) as api:
        with pytest.raises(WriteUncertain) as caught:
            await api.student(valid_token()).update_settings(UPDATE)
    assert caught.value.upstream_status is None


async def test_real_app_403_on_write_reaches_sdk_with_upstream_status(asgi_client, fake_diary):
    fake_diary.answers["update_settings"] = UpstreamError(upstream_status=403)

    # Ядро: 403 на записи — определённый отказ, а не неопределённость.
    with pytest.raises(UpstreamError) as caught:
        await asgi_client.student(valid_token()).update_settings(UPDATE)

    assert caught.value.upstream_status == 403
    assert not isinstance(caught.value, WriteUncertain)
