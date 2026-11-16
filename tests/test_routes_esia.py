"""Маршруты /v1/auth/esia*: контракт ответов и ошибок по спеку SDK.

Дневник — подставной: сами шаги ЕСИА проверяет tests/test_login_esia.py,
потоки — tests/test_login_flows.py и tests/test_login_service.py.
"""

import base64
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from diarysdk._port import CaptchaChallenge, EsiaStep, MfaChallenge, unsupported_step
from diarysdk.errors import (
    BadCaptcha,
    BadCode,
    BadCredentials,
    LoginBlocked,
    UpstreamError,
    UpstreamFormat,
    UpstreamTimeout,
)
from diarysdk.server.app import create_app
from diarysdk.server.keys import hash_key
from tests.conftest import KEY_HEADERS
from tests.fakes import FakeDiary, core_diary
from tests.tokens import valid_token

LOGIN_KEY = {"X-Api-Key": "login-key"}
SITE_KEY = {"X-Api-Key": "site-key"}
PASSWORD = "Пароль-госуслуг-42"
CODE = "246813"
ANSWER = "капча-ответ-7Q"
BODY = {"login": "ivanov", "password": PASSWORD}
JWT = valid_token()
SMS = MfaChallenge(kind="sms", contact="+7 *** ***-**-12", ttl=300, attempts_left=3)
IMAGE = CaptchaChallenge(kind="image", image=b"\x89PNG-1", image_type="image/png")
QUESTION = CaptchaChallenge(kind="question", question="Сколько будет два плюс два?")


class Session:
    def __init__(self, waiting):
        self.waiting = waiting
        self.closed = 0

    def close(self):
        self.closed += 1


@pytest.fixture
def session():
    return Session("mfa")


@pytest.fixture
def fake_diary(session):
    return FakeDiary(esia_start=(session, EsiaStep(mfa=SMS)), esia_code=JWT, esia_captcha=JWT)


@pytest.fixture
async def client(settings, keys_file, fake_diary):
    keys_file.write_text(
        f"tests {hash_key('test-key')}\n"
        f"bot {hash_key('login-key')} login\n"
        f"bot {hash_key('bot-read-key')}\n"
        f"site {hash_key('site-key')} login\n"
    )
    app = create_app(settings, diary=core_diary(fake_diary))
    async with AsyncClient(transport=ASGITransport(app), base_url="http://t") as c:
        yield c


async def start(client, headers=LOGIN_KEY):
    return await client.post("/v1/auth/esia", json=BODY, headers=headers)


async def started(client):
    response = await start(client)
    assert response.status_code == 202, response.text
    return response.json()["flow_id"]


async def test_start_with_mfa_is_202_login_step(client, fake_diary):
    response = await start(client)

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"flow_id", "step", "expires_at", "mfa", "captcha"}
    assert body["step"] == "mfa"
    assert body["captcha"] is None
    assert body["mfa"] == {
        "kind": "sms",
        "contact": "+7 *** ***-**-12",
        "ttl": 300,
        "attempts_left": 3,
    }
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert timedelta(minutes=4) < expires_at - datetime.now(UTC) <= timedelta(minutes=5)
    assert fake_diary.args["esia_start"] == ("ivanov", PASSWORD)
    assert response.headers["Cache-Control"] == "no-store"


async def test_start_done_at_once_is_200_token(client, fake_diary, session):
    fake_diary.answers["esia_start"] = (session, JWT)

    response = await start(client)

    assert response.status_code == 200
    assert response.json()["token"] == JWT
    assert response.json()["method"] == "esia"


async def test_code_gives_token(client, fake_diary, session):
    flow_id = await started(client)

    response = await client.post(
        f"/v1/auth/esia/{flow_id}/code", json={"code": CODE}, headers=LOGIN_KEY
    )

    assert response.status_code == 200
    assert set(response.json()) == {"token", "expires_at", "method"}
    assert response.json()["method"] == "esia"
    assert fake_diary.args["esia_code"] == (session, CODE)
    # Поток закончен: второй раз его нет.
    again = await client.post(
        f"/v1/auth/esia/{flow_id}/code", json={"code": CODE}, headers=LOGIN_KEY
    )
    assert (again.status_code, again.json()["error"]) == (404, "flow_expired")


async def test_captcha_flow_with_image_renew_and_answer(client, fake_diary, session):
    fresh = CaptchaChallenge(kind="image", image=b"\x89PNG-2", image_type="image/png")
    fake_diary.answers["esia_code"] = EsiaStep(captcha=IMAGE)
    fake_diary.answers["esia_captcha_renew"] = EsiaStep(captcha=fresh)
    flow_id = await started(client)

    step = await client.post(
        f"/v1/auth/esia/{flow_id}/code", json={"code": CODE}, headers=LOGIN_KEY
    )
    session.waiting = "captcha"
    renewed = await client.post(f"/v1/auth/esia/{flow_id}/captcha/renew", headers=LOGIN_KEY)
    done = await client.post(
        f"/v1/auth/esia/{flow_id}/captcha", json={"answer": ANSWER}, headers=LOGIN_KEY
    )

    assert step.status_code == 202
    captcha = step.json()["captcha"]
    assert set(captcha) == {"kind", "image_base64", "image_type", "question"}
    assert (captcha["kind"], captcha["image_type"], captcha["question"]) == (
        "image",
        "image/png",
        None,
    )
    assert base64.b64decode(captcha["image_base64"]) == b"\x89PNG-1"
    assert step.json()["mfa"] is None
    assert renewed.status_code == 202
    assert base64.b64decode(renewed.json()["captcha"]["image_base64"]) == b"\x89PNG-2"
    assert done.status_code == 200
    assert fake_diary.args["esia_captcha"] == (session, ANSWER)


async def test_question_captcha_step(client, fake_diary, session):
    fake_diary.answers["esia_start"] = (session, EsiaStep(captcha=QUESTION))

    response = await start(client)

    assert response.json()["captcha"] == {
        "kind": "question",
        "image_base64": None,
        "image_type": None,
        "question": "Сколько будет два плюс два?",
    }


async def test_cancel_is_204_and_idempotent(client, session):
    flow_id = await started(client)

    first = await client.delete(f"/v1/auth/esia/{flow_id}", headers=LOGIN_KEY)
    second = await client.delete(f"/v1/auth/esia/{flow_id}", headers=LOGIN_KEY)
    step = await client.post(
        f"/v1/auth/esia/{flow_id}/code", json={"code": CODE}, headers=LOGIN_KEY
    )

    assert (first.status_code, second.status_code) == (204, 204)
    assert first.content == b""
    assert session.closed == 1
    assert step.json()["error"] == "flow_expired"


async def test_foreign_consumer_gets_flow_expired(client, fake_diary, session):
    flow_id = await started(client)

    foreign = await client.post(
        f"/v1/auth/esia/{flow_id}/code", json={"code": CODE}, headers=SITE_KEY
    )
    unknown = await client.post(
        "/v1/auth/esia/no-such-flow/code", json={"code": CODE}, headers=LOGIN_KEY
    )
    cancel = await client.delete(f"/v1/auth/esia/{flow_id}", headers=SITE_KEY)

    assert (foreign.status_code, foreign.json()["error"]) == (404, "flow_expired")
    assert foreign.json() == unknown.json()
    assert cancel.status_code == 204
    assert session.closed == 0
    assert "esia_code" not in fake_diary.calls


async def test_bad_code_is_401_with_next_step(client, fake_diary):
    fake_diary.answers["esia_code"] = BadCode(
        step=MfaChallenge(kind="sms", contact=None, ttl=300, attempts_left=2)
    )
    flow_id = await started(client)

    response = await client.post(
        f"/v1/auth/esia/{flow_id}/code", json={"code": "111111"}, headers=LOGIN_KEY
    )

    assert response.status_code == 401
    body = response.json()
    assert set(body) == {"error", "message", "step"}
    assert body["error"] == "bad_code"
    assert body["step"]["flow_id"] == flow_id
    assert body["step"]["mfa"]["attempts_left"] == 2
    assert "111111" not in response.text


async def test_bad_captcha_is_401_with_fresh_captcha(client, fake_diary, session):
    fresh = CaptchaChallenge(kind="image", image=b"\x89PNG-2", image_type="image/png")
    fake_diary.answers["esia_start"] = (Session("captcha"), EsiaStep(captcha=IMAGE))
    fake_diary.answers["esia_captcha"] = BadCaptcha(step=fresh)
    flow_id = await started(client)

    response = await client.post(
        f"/v1/auth/esia/{flow_id}/captcha", json={"answer": ANSWER}, headers=LOGIN_KEY
    )

    assert response.status_code == 401
    assert response.json()["error"] == "bad_captcha"
    step = response.json()["step"]
    assert step["step"] == "captcha"
    assert base64.b64decode(step["captcha"]["image_base64"]) == b"\x89PNG-2"
    assert ANSWER not in response.text


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (BadCredentials(), 401, "bad_credentials"),
        (LoginBlocked(), 409, "login_blocked"),
        (unsupported_step("PUSH"), 422, "unsupported_step"),
        (UpstreamFormat(problems=["cookie aupd_token: нет в ответе"]), 502, "upstream_format"),
        (UpstreamError(upstream_status=503), 502, "upstream_error"),
        (UpstreamTimeout(), 504, "upstream_timeout"),
    ],
)
async def test_start_failures_follow_error_table(client, fake_diary, error, status, code):
    fake_diary.answers["esia_start"] = error

    response = await start(client)

    assert (response.status_code, response.json()["error"]) == (status, code)
    assert set(response.json()) <= {"error", "message", "upstream_status"}
    assert PASSWORD not in response.text


async def test_unsupported_step_names_what_esia_asked(client, fake_diary):
    fake_diary.answers["esia_start"] = unsupported_step("PUSH")

    response = await start(client)

    assert "PUSH" in response.json()["message"]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (LoginBlocked(), 409, "login_blocked"),
        (unsupported_step("SIGN"), 422, "unsupported_step"),
        (UpstreamFormat(problems=["x"]), 502, "upstream_format"),
        (UpstreamError(upstream_status=None), 502, "upstream_error"),
        (UpstreamTimeout(), 504, "upstream_timeout"),
    ],
)
async def test_code_failures_drop_flow(client, fake_diary, error, status, code):
    fake_diary.answers["esia_code"] = error
    flow_id = await started(client)

    response = await client.post(
        f"/v1/auth/esia/{flow_id}/code", json={"code": CODE}, headers=LOGIN_KEY
    )
    again = await client.post(
        f"/v1/auth/esia/{flow_id}/code", json={"code": CODE}, headers=LOGIN_KEY
    )

    assert (response.status_code, response.json()["error"]) == (status, code)
    assert again.json()["error"] == "flow_expired"


async def test_wrong_step_is_bad_request(client):
    flow_id = await started(client)

    response = await client.post(
        f"/v1/auth/esia/{flow_id}/captcha", json={"answer": ANSWER}, headers=LOGIN_KEY
    )

    assert (response.status_code, response.json()["error"]) == (400, "bad_request")
    assert ANSWER not in response.text


@pytest.mark.parametrize(
    ("path", "body", "secret"),
    [
        ("esia", {"login": "ivanov"}, None),
        ("esia", {"login": "ivanov", "password": [PASSWORD]}, PASSWORD),
        ("code", {}, None),
        ("code", {"code": "12ab56"}, "12ab56"),
        ("code", {"code": "1" * 40}, "1" * 40),
        ("code", {"code": 246813}, "246813"),
        ("code", {"code": "２４６８１３"}, "２４６８１３"),
        ("captcha", {"answer": ""}, None),
        ("captcha", {"answer": ANSWER * 50}, ANSWER),
        ("captcha", {"answer": [ANSWER]}, ANSWER),
    ],
)
async def test_bad_body_is_bad_request_without_echo(client, fake_diary, path, body, secret):
    flow_id = await started(client) if path != "esia" else None
    url = "/v1/auth/esia" if path == "esia" else f"/v1/auth/esia/{flow_id}/{path}"

    response = await client.post(url, json=body, headers=LOGIN_KEY)

    assert (response.status_code, response.json()["error"]) == (400, "bad_request")
    if secret:
        assert secret not in response.text


async def test_key_without_login_scope_is_forbidden_everywhere(client, fake_diary):
    flow_id = await started(client)
    other = {"X-Api-Key": "bot-read-key"}

    responses = [
        await client.post("/v1/auth/esia", json=BODY, headers=other),
        await client.post(f"/v1/auth/esia/{flow_id}/code", json={"code": CODE}, headers=other),
        await client.post(
            f"/v1/auth/esia/{flow_id}/captcha", json={"answer": ANSWER}, headers=other
        ),
        await client.post(f"/v1/auth/esia/{flow_id}/captcha/renew", headers=other),
        await client.delete(f"/v1/auth/esia/{flow_id}", headers=other),
        await client.post("/v1/auth/esia", json=BODY, headers=KEY_HEADERS),
    ]

    assert {(r.status_code, r.json()["error"]) for r in responses} == {(403, "forbidden_scope")}
    assert fake_diary.calls == ["esia_start"]


async def test_only_starts_count_against_login_limit(client, fake_diary, session):
    # Старты: 5 в минуту на потребителя, вместе с /password. Шаги начатого
    # входа (код, капча, обновление, отмена) их не тратят.
    fake_diary.answers["esia_code"] = BadCode(step=SMS)
    flow_id = await started(client)
    for _ in range(10):
        response = await client.post(
            f"/v1/auth/esia/{flow_id}/code", json={"code": CODE}, headers=LOGIN_KEY
        )
        assert response.json()["error"] == "bad_code"
    await client.delete(f"/v1/auth/esia/{flow_id}", headers=LOGIN_KEY)

    fake_diary.answers["esia_start"] = BadCredentials()
    codes = [(await start(client)).status_code for _ in range(4)]
    limited = await start(client)

    assert codes == [401] * 4
    assert (limited.status_code, limited.json()["error"]) == (429, "rate_limited")
    assert "Retry-After" in limited.headers
    other = await start(client, SITE_KEY)
    assert other.status_code == 401


async def test_fourth_open_flow_is_rate_limited(client, fake_diary):
    for _ in range(3):
        await started(client)

    response = await start(client)

    assert (response.status_code, response.json()["error"]) == (429, "rate_limited")
    assert int(response.headers["Retry-After"]) > 0
    assert fake_diary.calls == ["esia_start"] * 3


async def test_openapi_documents_esia_routes(client):
    spec = (await client.get("/openapi.json")).json()

    paths = spec["paths"]
    assert {
        "/v1/auth/esia",
        "/v1/auth/esia/{flow_id}/code",
        "/v1/auth/esia/{flow_id}/captcha",
        "/v1/auth/esia/{flow_id}/captcha/renew",
        "/v1/auth/esia/{flow_id}",
    } <= set(paths)
    assert set(paths["/v1/auth/esia"]["post"]["responses"]) >= {"200", "202"}
    assert "delete" in paths["/v1/auth/esia/{flow_id}"]
    schemas = spec["components"]["schemas"]
    assert {"LoginStep", "LoginMfa", "LoginCaptcha", "MfaCode", "CaptchaAnswer"} <= set(schemas)
    assert schemas["MfaCode"]["properties"]["code"]["format"] == "password"
    assert schemas["CaptchaAnswer"]["properties"]["answer"]["format"] == "password"


async def test_lifespan_sweeps_flows_and_closes_them_on_shutdown(settings, fake_diary, session):
    app = create_app(settings, diary=core_diary(fake_diary))

    async with app.router.lifespan_context(app):
        sweeper = app.state.login_sweeper
        assert not sweeper.done()
        flows = app.state.login_flows
        login = await app.state.diary.login.esia("ivanov", PASSWORD)
        flow = await flows.reserve("bot")
        await flows.activate(flow, login)

    # Остановка: уборщик снят, незаконченные входы закрыты.
    assert sweeper.cancelled()
    assert session.closed == 1


async def test_unsupported_step_hint_reaches_message(client, fake_diary):
    fake_diary.answers["esia_start"] = unsupported_step("MAX_QUIZ", hint="Настройте MAX")

    response = await start(client)

    assert "MAX_QUIZ" in response.json()["message"]
    assert "Настройте MAX" in response.json()["message"]
