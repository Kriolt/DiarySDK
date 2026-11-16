"""Маршруты /v1/auth: вход по паролю портала и сведения о токене.

Дневник — подставной Diary: сами шаги входа проверяет tests/test_login.py.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from diarysdk.errors import BadCredentials, UpstreamError, UpstreamFormat, UpstreamTimeout
from diarysdk.server.app import create_app
from diarysdk.server.keys import hash_key
from tests.conftest import KEY_HEADERS
from tests.fakes import FakeDiary, core_diary
from tests.tokens import make_token, valid_token

LOGIN_KEY = {"X-Api-Key": "login-key"}
OTHER_LOGIN_KEY = {"X-Api-Key": "site-key"}
PASSWORD = "Пароль-секрет-42"
BODY = {"login": "ivanov", "password": PASSWORD}
JWT = valid_token()


@pytest.fixture
def fake_diary():
    return FakeDiary(password_login=JWT)


@pytest.fixture
async def client(settings, keys_file, fake_diary):
    # tests — ключ без разрешения login (как в conftest), bot и site — с ним;
    # у bot есть и второй ключ, без разрешения.
    keys_file.write_text(
        f"tests {hash_key('test-key')}\n"
        f"bot {hash_key('login-key')} login\n"
        f"bot {hash_key('bot-read-key')}\n"
        f"site {hash_key('site-key')} login\n"
    )
    app = create_app(settings, diary=core_diary(fake_diary))
    async with AsyncClient(transport=ASGITransport(app), base_url="http://t") as c:
        yield c


async def test_password_login_returns_token(client, fake_diary):
    response = await client.post("/v1/auth/password", json=BODY, headers=LOGIN_KEY)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"token", "expires_at", "method"}
    assert (body["token"], body["method"]) == (JWT, "password")
    # Срок — из exp самого JWT (valid_token: через час).
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert timedelta(minutes=50) < expires_at - datetime.now(UTC) <= timedelta(hours=1)
    assert fake_diary.args["password_login"] == ("ivanov", PASSWORD)
    assert response.headers["Cache-Control"] == "no-store"


async def test_password_login_needs_no_user_token(client):
    # Токена у входящего ещё нет; старый просроченный не мешает.
    expired = make_token(datetime.now(UTC) - timedelta(hours=1))
    headers = {**LOGIN_KEY, "Authorization": f"Bearer {expired}"}

    response = await client.post("/v1/auth/password", json=BODY, headers=headers)

    assert response.status_code == 200


async def test_key_without_login_scope_is_forbidden(client, fake_diary):
    response = await client.post("/v1/auth/password", json=BODY, headers=KEY_HEADERS)

    assert response.status_code == 403
    assert response.json()["error"] == "forbidden_scope"
    assert fake_diary.calls == []


async def test_missing_key_is_bad_api_key(client, fake_diary):
    response = await client.post("/v1/auth/password", json=BODY)

    assert response.status_code == 403
    assert response.json()["error"] == "bad_api_key"
    assert fake_diary.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"login": "ivanov"},
        {"password": PASSWORD},
        {"login": "", "password": PASSWORD},
        {"login": "   ", "password": PASSWORD},
        {"login": " \t\n", "password": PASSWORD},
        {"login": "ivanov", "password": ""},
        {"login": ["ivanov"], "password": PASSWORD},
        {"login": "ivanov", "password": [PASSWORD]},
        {"login": "ivanov", "password": PASSWORD * 100},
    ],
)
async def test_bad_body_is_bad_request_without_echo(client, fake_diary, body):
    response = await client.post("/v1/auth/password", json=body, headers=LOGIN_KEY)

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert PASSWORD not in response.text
    assert "ivanov" not in response.text
    assert fake_diary.calls == []


async def test_body_that_is_not_json_is_bad_request(client):
    response = await client.post(
        "/v1/auth/password",
        content=f"login=ivanov&password={PASSWORD}".encode(),
        headers={**LOGIN_KEY, "Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert PASSWORD not in response.text


async def test_bad_key_comes_before_broken_json(client, fake_diary):
    # Без ключа тело даже не разбирается: 403, а не 400 про JSON.
    response = await client.post(
        "/v1/auth/password",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 403
    assert response.json()["error"] == "bad_api_key"
    assert fake_diary.calls == []


async def test_invalid_body_does_not_spend_login_starts(client, fake_diary):
    # Отказ по телу в ПДн не уходит никуда — счётчик стартов не тратится.
    for _ in range(6):
        bad = await client.post("/v1/auth/password", json={"login": "x"}, headers=LOGIN_KEY)
        assert bad.status_code == 400
    broken = await client.post(
        "/v1/auth/esia",
        content=b"{",
        headers={**LOGIN_KEY, "Content-Type": "application/json"},
    )
    assert broken.status_code == 400

    response = await client.post("/v1/auth/password", json=BODY, headers=LOGIN_KEY)

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (BadCredentials(), 401, "bad_credentials"),
        (UpstreamFormat(problems=["authentication_token: нет в ответе"]), 502, "upstream_format"),
        (UpstreamError(upstream_status=503), 502, "upstream_error"),
        (UpstreamError(upstream_status=None), 502, "upstream_error"),
        (UpstreamTimeout(), 504, "upstream_timeout"),
    ],
)
async def test_login_failures_follow_error_table(client, fake_diary, error, status, code):
    fake_diary.answers["password_login"] = error

    response = await client.post("/v1/auth/password", json=BODY, headers=LOGIN_KEY)

    assert response.status_code == status
    assert response.json()["error"] == code
    assert PASSWORD not in response.text


async def test_login_starts_are_limited_to_five_per_minute(client, fake_diary):
    fake_diary.answers["password_login"] = BadCredentials()

    codes = [
        (await client.post("/v1/auth/password", json=BODY, headers=LOGIN_KEY)).status_code
        for _ in range(5)
    ]
    limited = await client.post("/v1/auth/password", json=BODY, headers=LOGIN_KEY)

    assert codes == [401] * 5
    assert limited.status_code == 429
    assert limited.json()["error"] == "rate_limited"
    # Новый старт — через 60/5 = 12 секунд.
    assert 11 <= int(limited.headers["Retry-After"]) <= 12
    assert fake_diary.calls == ["password_login"] * 5


async def test_login_limit_is_per_consumer_and_only_for_starts(client):
    for _ in range(6):
        await client.post("/v1/auth/password", json=BODY, headers=LOGIN_KEY)

    other = await client.post("/v1/auth/password", json=BODY, headers=OTHER_LOGIN_KEY)
    info = await client.get(
        "/v1/auth/token", headers={**LOGIN_KEY, "Authorization": f"Bearer {JWT}"}
    )

    assert other.status_code == 200
    assert info.status_code == 200


async def test_refused_scope_does_not_spend_login_starts(client):
    # Тот же потребитель bot, но ключ без разрешения: отказ по разрешению
    # стартом входа не считается.
    for _ in range(6):
        refused = await client.post(
            "/v1/auth/password", json=BODY, headers={"X-Api-Key": "bot-read-key"}
        )
        assert refused.status_code == 403

    response = await client.post("/v1/auth/password", json=BODY, headers=LOGIN_KEY)

    assert response.status_code == 200


async def test_token_info_decodes_token_without_diary(client, fake_diary):
    token = make_token(datetime.now(UTC) + timedelta(hours=2), sub="1000001", rol="student,parent")

    response = await client.get(
        "/v1/auth/token", headers={**KEY_HEADERS, "Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"expires_at", "expires_in", "subject_id", "roles"}
    assert 7190 <= body["expires_in"] <= 7200
    assert body["subject_id"] == "1000001"
    assert body["roles"] == ["student", "parent"]
    assert fake_diary.calls == []
    assert response.headers["Cache-Control"] == "no-store"


async def test_token_info_without_optional_claims(client):
    token = make_token(datetime.now(UTC) + timedelta(hours=1))

    response = await client.get(
        "/v1/auth/token", headers={**KEY_HEADERS, "Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["subject_id"] is None
    assert response.json()["roles"] == []


@pytest.mark.parametrize(
    ("headers", "status", "code"),
    [
        ({}, 403, "bad_api_key"),
        (KEY_HEADERS, 401, "token_missing"),
        (
            {
                **KEY_HEADERS,
                "Authorization": f"Bearer {make_token(datetime.now(UTC) - timedelta(minutes=1))}",
            },
            401,
            "token_expired",
        ),
        ({**KEY_HEADERS, "Authorization": "Bearer a.b"}, 401, "token_invalid"),
    ],
)
async def test_token_info_needs_key_and_live_token(client, headers, status, code):
    response = await client.get("/v1/auth/token", headers=headers)

    assert response.status_code == status
    assert response.json()["error"] == code


async def test_openapi_documents_auth_routes(client):
    spec = (await client.get("/openapi.json")).json()

    assert {"/v1/auth/password", "/v1/auth/token"} <= set(spec["paths"])
    schemas = spec["components"]["schemas"]
    assert {"TokenResponse", "TokenInfo", "PasswordLogin"} <= set(schemas)
    assert schemas["PasswordLogin"]["properties"]["password"]["format"] == "password"
