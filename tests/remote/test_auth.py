"""Вход в SDK: password/esia, потоки, ошибки и полный цикл через настоящее приложение."""

import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport

from diarysdk import (
    BadCaptcha,
    BadCode,
    BadCredentials,
    FlowExpired,
    NetworkError,
    RateLimited,
    Token,
    TokenExpired,
    UpstreamFormat,
    UpstreamTimeout,
    WriteUncertain,
)
from diarysdk._port import EsiaStep, MfaChallenge
from diarysdk.models.school import School
from diarysdk.remote import RemoteLoginFlow
from tests.remote.esia import FRESH, LOGIN_KEY, SMS, Session
from tests.remote.helpers import remote_diary
from tests.tokens import make_token, valid_token


async def test_password_gives_token(api, jwt):
    token = await api.login.password("ivanov", "секрет")

    assert isinstance(token, Token)
    assert (token.value, token.method) == (jwt, "password")
    assert token.expires_in() > timedelta(minutes=50)
    assert "секрет" not in repr(token)


async def test_bad_credentials(api, fake_diary):
    fake_diary.answers["password_login"] = BadCredentials()
    with pytest.raises(BadCredentials) as caught:
        await api.login.password("ivanov", "не тот")
    assert caught.value.status == 401


async def test_esia_done_at_once_is_token(api, fake_diary, session, jwt):
    fake_diary.answers["esia_start"] = (session, jwt)
    token = await api.login.esia("ivanov", "p")
    assert (token.value, token.method) == (jwt, "esia")


async def test_flow_exposes_step_data_and_bytes_image(api):
    flow = await api.login.esia("ivanov", "p")

    assert isinstance(flow, RemoteLoginFlow)
    assert flow.kind == "captcha"
    assert flow.mfa is None
    assert flow.captcha.kind == "image"
    assert flow.captcha.image == b"\x89PNG-1"
    assert flow.captcha.image_type == "image/png"
    assert flow.expires_at > datetime.now(UTC)
    assert "PNG" not in repr(flow)


async def test_full_cycle_captcha_mfa_read_expiry_hook_login_again(
    app, fake_diary, session, jwt, monkeypatch
):
    asked = []

    async def ask_to_login(token):
        asked.append(token)

    async with remote_diary(
        "http://t", LOGIN_KEY, transport=ASGITransport(app), on_token_expired=ask_to_login
    ) as api:
        # Вход: капча, потом код из SMS.
        flow = await api.login.esia("ivanov", "пароль")
        assert flow.kind == "captcha"
        flow = await flow.renew_captcha()
        assert flow.captcha.image == b"\x89PNG-2"
        flow = await flow.answer_captcha("ответ")
        assert flow.kind == "mfa"
        assert (flow.mfa.kind, flow.mfa.attempts_left) == ("sms", 3)
        token = await flow.submit_code("246813")
        assert isinstance(token, Token)
        assert token.method == "esia"

        # Чтение с этим токеном.
        fake_diary.answers["school"] = School(name="Гимназия")
        student = api.student(token)
        assert (await student.school()).name == "Гимназия"
        assert asked == []

        # Срок вышел: сервер отвечает token_expired, хук зовётся один раз.
        later = datetime.now(UTC) + timedelta(hours=2)

        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return later

        with monkeypatch.context() as expired_clock:
            expired_clock.setattr("diarysdk.server.edge.auth.datetime", Later)
            with pytest.raises(TokenExpired):
                await student.me()
        assert asked == [token]

        # Повторный вход (его делает потребитель сам) и чтение новым токеном.
        fake_diary.answers["esia_start"] = (Session("mfa"), make_token(later, sub="1000001"))
        again = await api.login.esia("ivanov", "пароль")
        assert isinstance(again, Token)
        assert again.expires_at > token.expires_at
    assert fake_diary.args["esia_captcha"] == (session, "ответ")
    assert fake_diary.args["esia_code"] == (session, "246813")


async def test_bad_code_carries_updated_flow_for_retry(api, fake_diary, session, jwt):
    fake_diary.answers["esia_start"] = (Session("mfa"), EsiaStep(mfa=SMS))
    fake_diary.answers["esia_code"] = BadCode(
        step=MfaChallenge(kind="sms", contact=None, ttl=300, attempts_left=2)
    )
    flow = await api.login.esia("ivanov", "p")

    with pytest.raises(BadCode) as caught:
        await flow.submit_code("111111")

    retry = caught.value.flow
    assert retry is flow
    assert retry.mfa.attempts_left == 2
    fake_diary.answers["esia_code"] = jwt
    token = await retry.submit_code("246813")
    assert isinstance(token, Token)


async def test_bad_captcha_carries_fresh_captcha(api, fake_diary):
    fake_diary.answers["esia_captcha"] = BadCaptcha(step=FRESH)
    flow = await api.login.esia("ivanov", "p")

    with pytest.raises(BadCaptcha) as caught:
        await flow.answer_captcha("не то")

    assert caught.value.flow.captcha.image == b"\x89PNG-2"
    assert "не то" not in repr(caught.value) + repr(caught.value.flow)


async def test_cancel_then_flow_is_gone(api, session):
    flow = await api.login.esia("ivanov", "p")

    assert await flow.close() is None
    assert await flow.close() is None  # повторно — не ошибка
    with pytest.raises(FlowExpired):
        await flow.answer_captcha("x")
    assert session.closed == 1


async def test_wrong_kind_of_step_is_bad_request_flow_intact(api):
    from diarysdk import BadRequest

    flow = await api.login.esia("ivanov", "p")
    with pytest.raises(BadRequest):
        await flow.submit_code("123456")


async def test_flow_with_totp_has_no_contact():
    state = {
        "flow_id": "f1",
        "step": "mfa",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        "mfa": {"kind": "totp", "contact": None, "ttl": 30, "attempts_left": 3},
        "captcha": None,
    }
    transport = httpx.MockTransport(lambda r: httpx.Response(202, json=state))
    async with remote_diary("http://t", "k", transport=transport) as api:
        flow = await api.login.esia("a", "b")
    assert flow.mfa.contact is None


async def test_cycle_with_bad_code_flow():
    steps = []
    expires = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    step = {
        "flow_id": "f1",
        "step": "mfa",
        "expires_at": expires,
        "mfa": {"kind": "sms", "contact": None, "ttl": 300, "attempts_left": 2},
        "captcha": None,
    }
    jwt = valid_token()

    def handler(request):
        steps.append((request.method, request.url.path, request.content))
        if request.url.path.endswith("/code"):
            if len(steps) == 2:
                return httpx.Response(401, json={"error": "bad_code", "message": "m", "step": step})
            return httpx.Response(200, json={"token": jwt, "expires_at": expires, "method": "esia"})
        return httpx.Response(202, json=step)

    async with remote_diary("http://t", "k", transport=httpx.MockTransport(handler)) as api:
        flow = await api.login.esia("a", "b")
        with pytest.raises(BadCode) as caught:
            await flow.submit_code("1111")
        token = await caught.value.flow.submit_code("2222")
    assert token.method == "esia"
    assert [s[1] for s in steps] == ["/v1/auth/esia"] + ["/v1/auth/esia/f1/code"] * 2


async def test_bad_step_in_error_body_leaves_flow_none():
    transport = httpx.MockTransport(
        lambda r: httpx.Response(401, json={"error": "bad_code", "message": "m", "step": "junk"})
    )
    async with remote_diary("http://t", "k", transport=transport) as api:
        with pytest.raises(BadCode) as caught:
            await api.login.password("a", "b")
    assert caught.value.flow is None


# --- сбои шага входа: не WriteUncertain, не повторяются ---


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (httpx.Response(504, json={"error": "upstream_timeout", "message": "m"}), UpstreamTimeout),
        (httpx.ConnectError("boom"), NetworkError),
    ],
)
async def test_login_failure_is_upstream_not_write_uncertain(sleeps, answer, expected):
    calls = []

    def handler(request):
        calls.append(request)
        if isinstance(answer, Exception):
            raise answer
        return answer

    async with remote_diary("http://t", "k", transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(expected) as caught:
            await api.login.esia("a", "b")
    assert not isinstance(caught.value, WriteUncertain)
    assert len(calls) == 1


async def test_login_rate_limited_has_retry_after(sleeps):
    transport = httpx.MockTransport(
        lambda r: httpx.Response(
            429, json={"error": "rate_limited", "message": "m"}, headers={"Retry-After": "40"}
        )
    )
    async with remote_diary("http://t", "k", transport=transport) as api:
        with pytest.raises(RateLimited) as caught:
            await api.login.password("a", "b")
    assert caught.value.retry_after == 40
    assert sleeps == []


async def test_password_not_in_request_repr():
    from diarysdk.remote import _core

    assert "пароль-секрет" not in repr(_core.password_login("a", "пароль-секрет"))


def test_token_method_defaults_to_jwt():
    assert Token(valid_token()).method == "jwt"
    assert "jwt" in repr(Token(valid_token()))


# --- хук, который упал ---


async def test_failing_hook_does_not_replace_token_expired(caplog):
    def broken(token):
        raise RuntimeError("секрет-в-тексте")

    transport = httpx.MockTransport(
        lambda r: httpx.Response(401, json={"error": "token_expired", "message": "m"})
    )
    async with remote_diary("http://t", "k", transport=transport, on_token_expired=broken) as api:
        with caplog.at_level(logging.WARNING, logger="diarysdk.remote"):
            with pytest.raises(TokenExpired) as caught:
                await api.student(valid_token()).me()
    assert any("RuntimeError" in note for note in caught.value.__notes__)
    assert "RuntimeError" in caplog.text
    assert "секрет-в-тексте" not in caplog.text


# --- M4: запасной разбор по статусу ---


@pytest.mark.parametrize(
    ("status", "headers", "body", "cls_name"),
    [
        (429, {"Retry-After": "7"}, b"<html>slow down</html>", "RateLimited"),
        (429, {}, b'{"error":"new_code","message":"m"}', "RateLimited"),
        (401, {}, b"Unauthorized", "AuthError"),
        (403, {}, b"Forbidden", "RemoteError"),
        (404, {}, b"<h1>404</h1>", "NotFound"),
    ],
)
async def test_unknown_error_body_falls_back_by_status(status, headers, body, cls_name):
    import diarysdk

    transport = httpx.MockTransport(lambda r: httpx.Response(status, content=body, headers=headers))
    async with remote_diary("http://t", "k", transport=transport, max_rate_wait=0) as api:
        with pytest.raises(getattr(diarysdk, cls_name)) as caught:
            await api.student(valid_token()).me()
    assert type(caught.value).__name__ == cls_name
    assert caught.value.status == status
    if status == 429 and headers:
        assert caught.value.retry_after == 7


def test_naive_expiry_is_treated_as_utc():
    from datetime import timedelta

    from diarysdk import Token

    naive = (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None)
    token = Token(valid_token(), naive)
    assert token.expires_at.tzinfo is UTC
    assert timedelta(minutes=59) < token.expires_in() < timedelta(hours=1, seconds=1)
    assert not token.is_expiring()


# --- B3/B4: битая картинка капчи ---


def _step_json(*, captcha, step="captcha"):
    return {
        "flow_id": "f1",
        "step": step,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        "mfa": None,
        "captcha": captcha,
    }


BROKEN_CAPTCHA = {"kind": "image", "image_base64": "@@@@", "image_type": "image/png"}


@pytest.mark.parametrize("error_code", ["bad_code", "bad_captcha"])
async def test_broken_captcha_in_error_step_keeps_bad_code_and_old_flow(error_code):
    # Битый шаг в теле ошибки не маскирует BadCode/BadCaptcha: поток остаётся прежним.
    flow_step = _step_json(captcha=None, step="mfa")
    flow_step["mfa"] = {"kind": "sms", "contact": None, "ttl": 300, "attempts_left": 2}

    def handler(request):
        if request.url.path == "/v1/auth/esia":
            return httpx.Response(202, json=flow_step)
        body = {"error": error_code, "message": "m", "step": _step_json(captcha=BROKEN_CAPTCHA)}
        return httpx.Response(401, json=body)

    async with remote_diary("http://t", "k", transport=httpx.MockTransport(handler)) as api:
        flow = await api.login.esia("a", "b")
        expected = BadCode if error_code == "bad_code" else BadCaptcha
        call = flow.submit_code if error_code == "bad_code" else flow.answer_captcha
        with pytest.raises(expected) as caught:
            await call("1")
    assert caught.value.flow is flow
    assert flow.mfa.attempts_left == 2


async def test_broken_captcha_on_202_cancels_server_flow():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(202, json=_step_json(captcha=BROKEN_CAPTCHA))

    async with remote_diary("http://t", "k", transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(UpstreamFormat):
            await api.login.esia("a", "b")
    assert seen == [("POST", "/v1/auth/esia"), ("DELETE", "/v1/auth/esia/f1")]


async def test_broken_captcha_on_renew_cancels_and_cancel_failure_is_not_swallowed_over_it():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.method == "DELETE":
            return httpx.Response(502, json={"error": "upstream_error", "message": "m"})
        if request.url.path.endswith("/renew"):
            return httpx.Response(202, json=_step_json(captcha=BROKEN_CAPTCHA))
        return httpx.Response(202, json=_step_json(captcha=None))

    async with remote_diary("http://t", "k", transport=httpx.MockTransport(handler)) as api:
        flow = await api.login.esia("a", "b")
        # Сбой самой отмены не подменяет исходную ошибку формата.
        with pytest.raises(UpstreamFormat):
            await flow.renew_captcha()
    assert seen[-1] == ("DELETE", "/v1/auth/esia/f1")
