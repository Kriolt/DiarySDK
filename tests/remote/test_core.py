import httpx
import pytest

from diarysdk import (
    BadApiKey,
    DiaryError,
    NetworkError,
    NotFound,
    RateLimited,
    TokenExpired,
    UpstreamError,
    UpstreamFormat,
    UpstreamTimeout,
    WriteUncertain,
)
from diarysdk.models.school import School
from diarysdk.remote._core import Request
from tests.remote.helpers import remote_diary
from tests.tokens import make_token, valid_token

GET_SCHOOL = Request("GET", "/v1/school", model=School)
POST_DONE = Request("POST", "/v1/homework/5/done")
ERROR_BODY = {"error": "upstream_error", "message": "x", "upstream_status": 500}


def mock(handler):
    return httpx.MockTransport(handler)


def async_client(handler, **kwargs):
    return remote_diary("http://t", "k", transport=mock(handler), **kwargs)


# --- против настоящего приложения ---


async def test_errors_of_real_app_map_to_classes(asgi_client, fake_diary):
    fake_diary.answers["school"] = NotFound()
    with pytest.raises(NotFound) as caught:
        await asgi_client._send(GET_SCHOOL, valid_token())
    assert (caught.value.status, caught.value.code) == (404, "not_found")


async def test_expired_token_and_bad_key(asgi_client, asgi_app):
    from datetime import UTC, datetime, timedelta

    from httpx import ASGITransport

    with pytest.raises(TokenExpired):
        await asgi_client._send(GET_SCHOOL, make_token(datetime.now(UTC) - timedelta(hours=1)))
    # Неверный ключ — отдельный клиент, а не правка настроек живого.
    async with remote_diary("http://t", "wrong", transport=ASGITransport(asgi_app)) as other:
        with pytest.raises(BadApiKey):
            await other._send(GET_SCHOOL, valid_token())


async def test_upstream_timeout_is_not_retried_for_write(asgi_client, fake_diary):
    fake_diary.answers["set_homework_done"] = WriteUncertain(cause=UpstreamTimeout())
    with pytest.raises(WriteUncertain) as caught:
        await asgi_client._send(POST_DONE, valid_token())
    assert caught.value.status == 504
    assert fake_diary.calls.count("set_homework_done") == 1


async def test_headers_carry_key_and_token():
    seen = []

    def handler(request):
        seen.append(request.headers)
        return httpx.Response(204)

    async with async_client(handler) as api:
        await api._send(Request("GET", "/x"), "tok")
    assert seen[0]["X-Api-Key"] == "k"
    assert seen[0]["Authorization"] == "Bearer tok"


# --- повторы ---


def flaky(*answers):
    calls = []

    def handler(request):
        calls.append(request)
        answer = answers[min(len(calls), len(answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer

    handler.calls = calls
    return handler


def ok():
    return httpx.Response(200, json={"name": "Школа"})


@pytest.mark.parametrize("status", [502, 503, 504])
async def test_get_retried_once_on_5xx(sleeps, status):
    handler = flaky(httpx.Response(status, json=ERROR_BODY), ok())
    async with async_client(handler) as api:
        assert isinstance(await api._send(GET_SCHOOL), School)
    assert len(handler.calls) == 2
    assert sleeps == [0.5]


async def test_get_retried_once_on_network_error(sleeps):
    handler = flaky(httpx.ConnectError("boom"), ok())
    async with async_client(handler) as api:
        await api._send(GET_SCHOOL)
    assert len(handler.calls) == 2


async def test_get_gives_up_after_one_retry(sleeps):
    handler = flaky(httpx.Response(503, json=ERROR_BODY))
    async with async_client(handler) as api:
        with pytest.raises(UpstreamError) as caught:
            await api._send(GET_SCHOOL)
    assert len(handler.calls) == 2
    assert caught.value.upstream_status == 500


async def test_get_network_failure_twice_is_network_error(sleeps):
    handler = flaky(httpx.ReadTimeout("slow"))
    async with async_client(handler) as api:
        with pytest.raises(NetworkError) as caught:
            await api._send(GET_SCHOOL)
    assert caught.value.status is None
    assert len(handler.calls) == 2


@pytest.mark.parametrize("status", [400, 401, 404, 500])
async def test_other_statuses_are_not_retried(sleeps, status):
    handler = flaky(httpx.Response(status, json={"error": "x", "message": "m"}))
    async with async_client(handler) as api:
        with pytest.raises(DiaryError):
            await api._send(GET_SCHOOL)
    assert len(handler.calls) == 1


@pytest.mark.parametrize("method", ["POST", "DELETE"])
@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(502, json={**ERROR_BODY, "uncertain": True}),
        httpx.Response(504, json={"error": "upstream_timeout", "message": "m", "uncertain": True}),
        httpx.Response(502, text="<html>Bad Gateway</html>"),
        httpx.ConnectError("boom"),
        httpx.ReadTimeout("slow"),
    ],
)
async def test_write_never_retried_and_uncertain(sleeps, method, answer):
    handler = flaky(answer)
    async with async_client(handler) as api:
        with pytest.raises(WriteUncertain):
            await api._send(Request(method, "/v1/homework/5/done"))
    assert len(handler.calls) == 1
    assert sleeps == []


async def test_write_503_is_plain_upstream_error(sleeps):
    handler = flaky(httpx.Response(503, json=ERROR_BODY))
    async with async_client(handler) as api:
        with pytest.raises(UpstreamError) as caught:
            await api._send(POST_DONE)
    assert not isinstance(caught.value, WriteUncertain)
    assert len(handler.calls) == 1


async def test_504_of_read_is_timeout_class(sleeps):
    handler = flaky(httpx.Response(504, json={"error": "upstream_timeout", "message": "m"}))
    async with async_client(handler) as api:
        with pytest.raises(UpstreamTimeout):
            await api._send(GET_SCHOOL)


# --- 429 ---


def limited(retry_after):
    return httpx.Response(
        429, json={"error": "rate_limited", "message": "m"}, headers={"Retry-After": retry_after}
    )


async def test_rate_limit_short_wait_is_waited_then_retried(sleeps):
    handler = flaky(limited("1"), ok())
    async with async_client(handler) as api:
        await api._send(GET_SCHOOL)
    assert sleeps == [1.0]
    assert len(handler.calls) == 2


async def test_rate_limit_long_wait_raises_with_retry_after(sleeps):
    handler = flaky(limited("30"))
    async with async_client(handler) as api:
        with pytest.raises(RateLimited) as caught:
            await api._send(GET_SCHOOL)
    assert caught.value.retry_after == 30
    assert sleeps == []
    assert len(handler.calls) == 1


async def test_rate_limit_waited_once_only(sleeps):
    handler = flaky(limited("1"))
    async with async_client(handler) as api:
        with pytest.raises(RateLimited):
            await api._send(GET_SCHOOL)
    assert len(handler.calls) == 2


async def test_max_rate_wait_is_configurable(sleeps):
    handler = flaky(limited("5"), ok())
    async with async_client(handler, max_rate_wait=5) as api:
        await api._send(GET_SCHOOL)
    assert sleeps == [5.0]


async def test_rate_limit_for_write_retried_because_not_processed(sleeps):
    handler = flaky(limited("1"), httpx.Response(204))
    async with async_client(handler) as api:
        await api._send(POST_DONE)
    assert len(handler.calls) == 2


# --- разбор ответов ---


async def test_non_json_error_body_falls_back_by_status():
    handler = flaky(httpx.Response(500, text="<html>oops</html>"))
    async with async_client(handler) as api:
        with pytest.raises(UpstreamError) as caught:
            await api._send(GET_SCHOOL)
    assert type(caught.value) is UpstreamError
    assert caught.value.message == "HTTP 500"
    assert caught.value.raw_code == "http_500"


async def test_unexpected_shape_is_upstream_format():
    handler = flaky(httpx.Response(200, json={"name": ["не", "строка"]}))
    async with async_client(handler) as api:
        with pytest.raises(UpstreamFormat):
            await api._send(GET_SCHOOL)


# --- терпимость к новым полям сервиса ---


async def test_extra_field_in_read_response_is_ignored():
    body = {"name": "Гимназия", "new_server_field": {"a": 1}}
    async with async_client(flaky(httpx.Response(200, json=body))) as api:
        result = await api._send(GET_SCHOOL)
    assert result.name == "Гимназия"
    assert not hasattr(result, "new_server_field")


def _step_body(**changes):
    from datetime import UTC, datetime, timedelta

    body = {
        "flow_id": "f1",
        "step": "mfa",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        "mfa": {"kind": "sms", "contact": "+7 *** 12", "ttl": 60, "attempts_left": 3},
        "captcha": None,
    }
    return {**body, **changes}


async def test_extra_field_in_login_step_is_ignored():
    body = _step_body(hint="новое", mfa={**_step_body()["mfa"], "channel": "x"})
    async with async_client(flaky(httpx.Response(202, json=body))) as api:
        flow = await api.login.esia("a", "b")
    assert flow.kind == "mfa"
    assert flow.mfa.attempts_left == 3


async def test_unknown_step_is_unsupported_step_not_upstream_format():
    from diarysdk import UnsupportedStep

    body = _step_body(step="passkey", mfa=None)
    async with async_client(flaky(httpx.Response(202, json=body))) as api:
        with pytest.raises(UnsupportedStep) as caught:
            await api.login.esia("a", "b")
    assert not isinstance(caught.value, UpstreamFormat)
    assert caught.value.status == 202


def test_default_timeout_outlasts_core_deadline():
    # Иначе шаг входа, удавшийся на 19.9 с, пропадёт у клиента, а SMS-код сгорит.
    import inspect

    from diarysdk import Diary
    from diarysdk.remote.client import DEFAULT_TIMEOUT

    deadline = inspect.signature(Diary.__init__).parameters["deadline"].default
    assert DEFAULT_TIMEOUT > deadline
