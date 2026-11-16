import httpx
import pytest
from httpx import ASGITransport

from diarysdk import (
    ForbiddenScope,
    NotFound,
    UnsupportedContact,
    UpstreamError,
    UpstreamTimeout,
    WriteUncertain,
)
from diarysdk.remote._core import update_contact
from diarysdk.server.app import create_app
from diarysdk.server.config import Settings
from diarysdk.server.keys import hash_key
from tests.conftest import API_KEY
from tests.fakes import core_diary
from tests.remote.helpers import remote_diary
from tests.tokens import valid_token

UPSTREAM_403 = {"error": "upstream_error", "message": "m", "upstream_status": 403}
# Так сервис помечает WriteUncertain: исход записи неизвестен.
UNCERTAIN = {"uncertain": True}
VALUE = "new@example.test"


class Handler:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def keys_file(tmp_path):
    path = tmp_path / "api-keys"
    path.write_text(f"tests {hash_key(API_KEY)} write_profile\n")
    return path


def async_client(handler):
    return remote_diary("http://t", "k", transport=httpx.MockTransport(handler))


def test_request_is_put_with_only_value():
    request = update_contact(2, VALUE)

    assert (request.method, request.path) == ("PUT", "/v1/identity/contacts/2")
    assert request.body == {"value": VALUE}
    assert request.uncertain
    assert VALUE not in repr(request)


async def test_real_app_passes_id_and_value(asgi_client, fake_diary):
    fake_diary.answers["update_contact"] = None

    assert await asgi_client.student(valid_token()).update_contact(2, VALUE) is None

    assert fake_diary.args["update_contact"][1:] == (2, VALUE)


@pytest.mark.parametrize(
    ("error", "expected"),
    [(NotFound(), NotFound), (UnsupportedContact(), UnsupportedContact)],
)
async def test_errors_map_to_sdk_errors(asgi_client, fake_diary, error, expected):
    fake_diary.answers["update_contact"] = error

    with pytest.raises(expected) as caught:
        await asgi_client.student(valid_token()).update_contact(2, VALUE)

    assert type(caught.value) is expected


async def test_real_app_403_on_write_reaches_sdk_with_upstream_status(asgi_client, fake_diary):
    fake_diary.answers["update_contact"] = UpstreamError(upstream_status=403)

    # Ядро: 403 на записи — определённый отказ, а не неопределённость.
    with pytest.raises(UpstreamError) as caught:
        await asgi_client.student(valid_token()).update_contact(2, VALUE)

    assert caught.value.upstream_status == 403
    assert not isinstance(caught.value, WriteUncertain)


async def test_key_without_write_profile_is_forbidden_scope(tmp_path, fake_diary, today):
    path = tmp_path / "plain"
    path.write_text(f"tests {hash_key(API_KEY)}\n")
    app = create_app(Settings(keys_file=path, version="x"), diary=core_diary(fake_diary))
    async with remote_diary("http://t", API_KEY, transport=ASGITransport(app)) as api:
        with pytest.raises(ForbiddenScope):
            await api.student(valid_token()).update_contact(2, VALUE)
    assert fake_diary.calls == []


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
            await api.student(valid_token()).update_contact(2, VALUE)
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
            await api.student(valid_token()).update_contact(2, VALUE)
    assert type(caught.value) is expected
    assert len(handler.calls) == 1
