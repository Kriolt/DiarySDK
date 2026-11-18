"""Сторожевой тест: в журнал не попадают токен, пароль, тела ответов, GUID и ID ученика.

Настоящее приложение целиком — край, сервис, gateway, _api и транспорт
httpx; дневник — MockTransport на фикстурах. Обходятся все маршруты
/v1 — в том числе те, что добавят потом: список берётся из схемы OpenAPI
самого приложения. Вход по паролю и через ЕСИА проверяется отдельно на
каждом исходе.
"""

import dataclasses
import io
import json
import logging
from contextlib import contextmanager
from datetime import date

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from diarysdk import _clock as clock
from diarysdk.client import Diary
from diarysdk.errors import UpstreamTimeout
from diarysdk.server import logs
from diarysdk.server.app import create_app
from diarysdk.server.keys import hash_key
from tests.conftest import API_KEY, AUTH_HEADERS, TOKEN
from tests.fakes import (
    DIARY_BASE,
    GUID,
    FakeDiary,
    FakeTransport,
    add_diary_routes,
    core_diary,
    fixture,
    mock_diary,
)

LOGIN = "ivanov-login@example.test"
PASSWORD = "Пароль-секрет-42"
LOGIN_BODY = {"login": LOGIN, "password": PASSWORD}
CODE = "one-time-code-77"
MFA_CODE = "246813"
ANSWER = "капча-ответ-7Q"
CONTACT = "+7 *** ***-**-12"
MAX_PARAM_CODE = "max-param-code-58"
ESIA_MFA = {
    "action": "ENTER_MFA",
    "mfa_details": {
        "type": "SMS",
        "otp_details": {
            "code_verified": False,
            "phone": CONTACT,
            "verify_attempts_left": 3,
            "verify_timeout_secs": 300,
            "renew_attempts_left": 5,
            "renew_timeout_secs": 60,
            "code_length": 6,
            "mfa_sms_auto_notification": True,
        },
    },
}
# После кода — предложение MAX (форма живого входа); его пропуск ведёт к капче.
ESIA_MAX_QUIZ = {
    "action": "MAX_QUIZ",
    "max_details": {
        "next_location": "/login/quiz-max",
        "ttl": 600,
        "parameters": {"masked_phone": CONTACT, "code": MAX_PARAM_CODE},
        "active_app": False,
        "already_setup_max": False,
        "quiz_version": 1,
    },
}
# Тело записи настроек и значения, которые не должны попасть в журнал.
SETTINGS_BODY = {"schedule_type": "full", "theme": {"color_pattern": "violet"}}
SETTINGS_SECRET = "секрет-группы-настроек-81"
# Отличимое значение известного поля: PATCH его не трогает, оно читается и
# уходит обратно в PUT, а в журнал попасть не должно.
ESTIMATION_SECRET = "секрет-вида-оценок-37"
# Новый и прежний адрес почты контакта: ни тот, ни другой в журнал не попадают.
CONTACT_NEW = "novyj-adres-93@secret-mail.test"
CONTACT_OLD = "staryj-adres-17@secret-mail.test"
CONTACT_BODY = {"value": CONTACT_NEW}
ESIA_IMAGE = {
    "action": "SOLVE_ANOMALY_REACTION",
    "reaction_details": {"type": "О.ЗД1", "guid": "guid-1"},
}


@pytest.fixture
def settings(settings, keys_file):
    # Ключ тестов с разрешениями login и write_profile: обход заходит и в /v1/auth/password.
    keys_file.write_text(f"tests {hash_key(API_KEY)} login,write_profile,acknowledge_journal\n")
    return settings


def use_http(monkeypatch, http: httpx.AsyncClient) -> None:
    """Приложение строит транспорт само: подставляем ему клиент без сети."""
    monkeypatch.setattr("diarysdk.server.app.Diary", lambda **options: Diary(http=http, **options))


@pytest.fixture
def routes():
    routes = FakeTransport()
    add_diary_routes(routes)
    # Вход по паролю: код в ответе sessions, токен — в куке callback.
    # В ответе sessions — контакты пользователя, как у портала.
    routes.add("/lms/api/sessions", {"email": LOGIN, "authentication_token": CODE})
    routes.add("/v3/auth/kauth/callback", b"", status=302, cookies={"aupd_token": TOKEN})
    add_esia_routes(routes)
    # Настройки со «своим» значением в неизвестном поле: оно читается и уходит
    # обратно в PUT, а в журнал попасть не должно.
    routes.add(
        "/api/usersettings/v1",
        {
            **fixture("user_settings.json"),
            "estimation_type": ESTIMATION_SECRET,
            "extra_key": SETTINGS_SECRET,
        },
    )
    # Карточка человека с почтой, которую обход правит (контакт 2).
    card = fixture("person_data.json")
    card["contacts"].append(
        {
            "id": 2,
            "person_id": GUID,
            "type_id": 7,
            "type": {"id": 7, "name": "Электронная почта"},
            "data": CONTACT_OLD,
            "default": False,
        }
    )
    routes.add(f"/api/persondata/v1/persons/{GUID}", card)
    routes.add(f"/api/persondata/v1/persons/{GUID}/contacts/2", b"")
    routes.add("/api/certificates/family/v1/certificates/statuses", [])
    routes.add("/api/certificates/family/v1/certificates", {"certificates": None, "count": 0})
    # mock_diary отвечает по пути без метода: и чтению, и отметке — пустой список.
    routes.add("/api/ej/core/family/v1/aware_journals", [])
    return routes


def add_esia_routes(routes):
    """ЕСИА на том же подставном сервере: код MFA, затем капча-картинка, затем DONE."""
    page = '<meta http-equiv="refresh" content="0;url=/aas/oauth2/ac?client_id=m&amp;state=s">'
    routes.add("/v3/auth/esia/login", page, content_type="text/html")
    routes.add("/aas/oauth2/ac", "ok", content_type="text/html")
    routes.add("/aas/oauth2/config", {})
    routes.add("/aas/oauth2/api/login", ESIA_MFA)
    routes.add("/aas/oauth2/api/login/otp/verify", ESIA_MAX_QUIZ)
    routes.add("/aas/oauth2/api/login/quiz-max/skip", ESIA_IMAGE)
    routes.add("/captcha/api/public/v2/type", {"captchaSession": "cs-1"})
    routes.add("/captcha/api/public/v2/renew", {"captchaSession": "cs-2"})
    routes.add("/captcha/api/public/v2/image", b"PNG", content_type="image/png")
    routes.add("/captcha/api/public/v2/verify", {"verify_token": "vt-1"})
    # DONE ведёт на callback портала, а тот ставит aupd_token.
    routes.add(
        "/aas/oauth2/api/anomaly/captcha/verify",
        {"action": "DONE", "redirect_url": "/v3/auth/kauth/callback?code=c-1"},
    )


@pytest.fixture
async def app(settings, routes, monkeypatch):
    # СНИЛС ученика в профиле пуст — значит, /v1/identity сходит и в карточку
    # человека, и в журнал попадёт и этот запрос.
    profile = fixture("profile.json")
    profile["children"][0]["snils"] = None
    routes.add("/api/family/web/v1/profile", profile)

    http = mock_diary(routes)
    use_http(monkeypatch, http)
    base = DIARY_BASE
    try:
        local = dataclasses.replace(
            settings,
            dnevnik_url=base,
            school_api_url=base,
            school_url=base,
            esia_url=base,
            # Обход всех маршрутов длиннее прежнего burst: лимит запросов не его предмет.
            rate_burst=100,
        )
        monkeypatch.setattr(clock, "today_msk", lambda: date(2026, 10, 24))
        app = create_app(local)
        # Обход переключает профиль на родительский перед маршрутами /v1/parent.
        app.state.test_routes = routes
        async with app.router.lifespan_context(app):
            yield app
    finally:
        await http.aclose()


def v1_routes(app) -> list[tuple[str, str]]:
    return [
        (
            method.upper(),
            path.replace("{lesson_id}", "20001")
            .replace("{homework_id}", "30001")
            .replace("{subject_id}", "101")
            .replace("{mark_id}", "10001")
            .replace("{contact_id}", "2")
            .replace("{group_id}", "5001"),
        )
        for path, methods in app.openapi()["paths"].items()
        if path.startswith("/v1/")
        for method in methods
    ]


def is_esia(path: str) -> bool:
    return path.startswith("/v1/auth/esia")


def is_parent(path: str) -> bool:
    # Справки — маршрут ученика, но только для токена родителя (child_id).
    return path.startswith("/v1/parent") or path == "/v1/certificates"


def as_parent(app) -> bool:
    """Профиль дневника — родительский: представитель ребёнка с СНИЛС владельца
    и GUID карточки из маршрутов. Возвращает True, чтобы стоять в условии."""
    routes = app.state.test_routes
    profile = fixture("profile.json")
    profile["children"][0]["snils"] = None
    profile["profile"].update(type="parent", snils=PARENT_SNILS)
    profile["children"][0]["representatives"] = [{"person_id": GUID, "snils": PARENT_SNILS}]
    routes.add("/api/family/web/v1/profile", profile)
    return True


async def walk(app) -> list[str]:
    """Обход всех маршрутов /v1; вернёт flow_id входов через ЕСИА."""
    transport = ASGITransport(app)
    async with AsyncClient(transport=transport, base_url="http://t", headers=AUTH_HEADERS) as c:
        # Сначала маршруты ученика, потом родителя — уже с профилем родителя.
        for method, path in sorted(v1_routes(app), key=lambda r: is_parent(r[1])):
            if is_esia(path):
                continue
            if is_parent(path) and not as_parent(app):
                continue
            body = LOGIN_BODY if path == "/v1/auth/password" else None
            if (method, path) in (("PATCH", "/v1/settings"), ("PATCH", "/v1/parent/settings")):
                body = SETTINGS_BODY
            if (method, path) in (
                ("PUT", "/v1/identity/contacts/2"),
                ("PUT", "/v1/parent/identity/contacts/2"),
            ):
                body = CONTACT_BODY
            child = path in ("/v1/parent/journal-acks", "/v1/certificates")
            params = {"child_id": 9001} if child else None
            if (method, path) == ("POST", "/v1/parent/journal-acks"):
                body, params = {"child_id": 9001}, None
            response = await c.request(method, path, json=body, params=params)
            assert response.status_code in (200, 204), (method, path, response.text)
        covered, flow_ids = await esia_walk(c)
    assert covered == {(m, p) for m, p in v1_routes(app) if is_esia(p)}
    return flow_ids


async def esia_walk(c) -> tuple[set[tuple[str, str]], list[str]]:
    """Вход через ЕСИА целиком (код, капча, новая капча, ответ) и отмена второго."""
    covered = set()

    async def call(method, template, flow_id=None, body=None, expect=202):
        response = await c.request(method, template.replace("{flow_id}", flow_id or ""), json=body)
        assert response.status_code == expect, (method, template, response.text)
        covered.add((method, template))
        return response

    first = (await call("POST", "/v1/auth/esia", body=LOGIN_BODY)).json()["flow_id"]
    await call("POST", "/v1/auth/esia/{flow_id}/code", first, {"code": MFA_CODE})
    await call("POST", "/v1/auth/esia/{flow_id}/captcha/renew", first)
    await call("POST", "/v1/auth/esia/{flow_id}/captcha", first, {"answer": ANSWER}, 200)
    second = (await call("POST", "/v1/auth/esia", body=LOGIN_BODY)).json()["flow_id"]
    await call("DELETE", "/v1/auth/esia/{flow_id}", second, expect=204)
    return covered, [first, second]


@contextmanager
def captured_log():
    """Журнал приложения в том виде, в каком он уходит в stdout: JSON-строки."""
    stream = io.StringIO()
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    logs.configure(stream=stream)
    try:
        yield stream
    finally:
        root.handlers, level = saved
        root.setLevel(level)


async def test_walk_covers_every_endpoint_of_the_contract(app):
    assert {path for _, path in v1_routes(app)} == {
        "/v1/me",
        "/v1/me/avatar",
        "/v1/school",
        "/v1/marks",
        "/v1/marks/10001",
        "/v1/subjects",
        "/v1/subjects/101",
        "/v1/rating",
        "/v1/rating/subjects",
        "/v1/rating/history",
        "/v1/schedule",
        "/v1/lessons/20001",
        "/v1/homework",
        "/v1/homework/30001/done",
        "/v1/exams",
        "/v1/final-marks",
        "/v1/identity",
        "/v1/identity/contacts/2",
        "/v1/notifications",
        "/v1/periods",
        "/v1/curriculum",
        "/v1/school/teachers",
        "/v1/academic-debts",
        "/v1/groups/5001/program",
        "/v1/subjects/101/topics",
        "/v1/control-works",
        "/v1/final-marks/file",
        "/v1/certificates",
        "/v1/settings",
        "/v1/auth/password",
        "/v1/auth/esia",
        "/v1/auth/esia/{flow_id}/code",
        "/v1/auth/esia/{flow_id}/captcha",
        "/v1/auth/esia/{flow_id}/captcha/renew",
        "/v1/auth/esia/{flow_id}",
        "/v1/auth/token",
        "/v1/parent/me",
        "/v1/parent/children",
        "/v1/parent/identity",
        "/v1/parent/avatar",
        "/v1/parent/settings",
        "/v1/parent/identity/contacts/2",
        "/v1/parent/journal-acks",
    }


PARENT_SNILS = "000-000-000 01"


def _values(data):
    if isinstance(data, dict):
        for value in data.values():
            yield from _values(value)
    elif isinstance(data, list):
        for value in data:
            yield from _values(value)
    else:
        yield data


async def test_log_has_no_token_bodies_guid_or_student_id(app):
    with captured_log() as stream:
        flow_ids = await walk(app)

    text = stream.getvalue()
    assert TOKEN not in text
    secrets = [PASSWORD, LOGIN, CODE, MFA_CODE, ANSWER, CONTACT, MAX_PARAM_CODE, *flow_ids]
    for value in [
        GUID,
        SETTINGS_SECRET,
        ESTIMATION_SECRET,
        CONTACT_NEW,
        CONTACT_OLD,
        "Тестов",
        "Алгебра",
        "Квадратные уравнения",
        "111-222-333 44",
        PARENT_SNILS,
        *secrets,
    ]:
        assert value not in text, value
    records = [json.loads(line) for line in text.splitlines()]
    assert any(r["message"] == "diary_call" for r in records)
    ids = {9001, 7001, 4001, 3001}  # student_id, profile_id, class_unit_id, school_id
    for record in records:
        assert not ids & {v for v in _values(record) if isinstance(v, int)}, record
        assert not {str(i) for i in ids} & {v for v in _values(record) if isinstance(v, str)}


def assert_no_credentials(text: str, *more: str) -> None:
    # Логин и пароль — и как есть, и в JSON-экранировании (\\uXXXX).
    for value in (PASSWORD, LOGIN, CODE, TOKEN, MFA_CODE, ANSWER, CONTACT, MAX_PARAM_CODE, *more):
        assert value not in text, value
        assert json.dumps(value)[1:-1] not in text, value
    assert any(json.loads(line)["message"] == "request" for line in text.splitlines())


async def login_once(app, body=LOGIN_BODY):
    transport = ASGITransport(app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t", headers=AUTH_HEADERS) as c:
        return await c.post("/v1/auth/password", json=body)


@pytest.mark.parametrize(
    ("path", "answer", "status", "code"),
    [
        ("/lms/api/sessions", {"status": 401, "body": {"error": "bad"}}, 401, "bad_credentials"),
        ("/lms/api/sessions", {"body": {"errors": ["нет такого"]}}, 401, "bad_credentials"),
        ("/lms/api/sessions", {"body": {"email": LOGIN}}, 502, "upstream_format"),
        (
            "/lms/api/sessions",
            {"body": "<html>", "content_type": "text/html"},
            502,
            "upstream_format",
        ),
        ("/lms/api/sessions", {"status": 503, "body": PASSWORD}, 502, "upstream_error"),
        ("/v3/auth/kauth/callback", {"status": 302, "body": b""}, 502, "upstream_format"),
        (
            "/v3/auth/kauth/callback",
            {"status": 302, "body": b"", "cookies": {"aupd_token": PASSWORD.encode().hex()}},
            502,
            "upstream_format",
        ),
        ("/v3/auth/kauth/callback", {"status": 401, "body": b""}, 502, "upstream_error"),
    ],
)
async def test_failed_password_login_keeps_credentials_out_of_log(
    app, routes, path, answer, status, code
):
    routes.add(path, **answer)

    with captured_log() as stream:
        response = await login_once(app)

    assert (response.status_code, response.json()["error"]) == (status, code)
    assert PASSWORD not in response.text
    assert_no_credentials(stream.getvalue())


async def test_bad_body_keeps_credentials_out_of_log_and_answer(app):
    with captured_log() as stream:
        response = await login_once(app, {"login": LOGIN, "password": [PASSWORD]})

    assert response.status_code == 400
    assert PASSWORD not in response.text
    assert LOGIN not in response.text
    assert_no_credentials(stream.getvalue())


async def test_rate_limited_login_keeps_credentials_out_of_log(app):
    with captured_log() as stream:
        for _ in range(5):
            await login_once(app)
        response = await login_once(app)

    assert response.status_code == 429
    assert_no_credentials(stream.getvalue())


@pytest.mark.parametrize("path", ["/v1/auth/password", "/v1/auth/esia"])
async def test_unreachable_portal_keeps_credentials_out_of_log(settings, path, monkeypatch):
    def refuse(request):
        raise httpx.ConnectError(f"отказ для {request.url}")

    use_http(monkeypatch, httpx.AsyncClient(transport=httpx.MockTransport(refuse)))
    base = DIARY_BASE
    app = create_app(dataclasses.replace(settings, dnevnik_url=base, esia_url=base))

    async with app.router.lifespan_context(app):
        with captured_log() as stream:
            transport = ASGITransport(app, raise_app_exceptions=False)
            async with AsyncClient(
                transport=transport, base_url="http://t", headers=AUTH_HEADERS
            ) as c:
                response = await c.post(path, json=LOGIN_BODY)

    assert (response.status_code, response.json()["error"]) == (502, "upstream_error")
    assert_no_credentials(stream.getvalue())


@pytest.mark.parametrize(
    "error",
    [
        UpstreamTimeout(),
        # Ошибка, которой мы не ждали, с паролем в тексте: в журнал идёт
        # только её тип.
        RuntimeError(f"упало на {LOGIN}:{PASSWORD}"),
    ],
)
async def test_timeout_and_crash_keep_credentials_out_of_log(settings, error):
    app = create_app(settings, diary=core_diary(FakeDiary(password_login=error)))

    with captured_log() as stream:
        response = await login_once(app)

    assert response.status_code in (500, 504)
    assert PASSWORD not in response.text
    assert_no_credentials(stream.getvalue())


# --- Вход через ЕСИА: каждый исход ---


async def esia_until(app, stage, *, code=MFA_CODE, answer=ANSWER):
    """Старт, затем код (stage code/captcha), затем капча (stage captcha).
    Вернёт последний ответ и все flow_id, что видел."""
    transport = ASGITransport(app, raise_app_exceptions=False)
    flow_ids = []
    async with AsyncClient(transport=transport, base_url="http://t", headers=AUTH_HEADERS) as c:
        response = await c.post("/v1/auth/esia", json=LOGIN_BODY)
        if response.status_code != 202:
            return response, flow_ids
        flow_id = response.json()["flow_id"]
        flow_ids.append(flow_id)
        if stage in ("code", "captcha"):
            response = await c.post(f"/v1/auth/esia/{flow_id}/code", json={"code": code})
        if stage == "captcha" and response.status_code == 202:
            response = await c.post(f"/v1/auth/esia/{flow_id}/captcha", json={"answer": answer})
    return response, flow_ids


@pytest.mark.parametrize(
    ("stage", "path", "answer", "status", "code"),
    [
        ("start", "/aas/oauth2/api/login", {"body": {"failed": "INVALID"}}, 401, "bad_credentials"),
        ("start", "/aas/oauth2/api/login", {"status": 401, "body": b""}, 401, "bad_credentials"),
        ("start", "/aas/oauth2/api/login", {"body": {"failed": "LOCKED"}}, 409, "login_blocked"),
        ("start", "/aas/oauth2/api/login", {"body": {"action": "PUSH"}}, 422, "unsupported_step"),
        (
            "start",
            "/aas/oauth2/api/login",
            {"body": {"action": "ENTER_MFA", "mfa_details": {"type": "PUSH"}}},
            422,
            "unsupported_step",
        ),
        (
            "start",
            "/aas/oauth2/api/login",
            {"status": 503, "body": PASSWORD},
            502,
            "upstream_error",
        ),
        (
            "start",
            "/aas/oauth2/api/login",
            {"body": "<html>", "content_type": "text/html"},
            502,
            "upstream_format",
        ),
        (
            "start",
            "/v3/auth/esia/login",
            {"body": "<html>", "content_type": "text/html"},
            502,
            "upstream_format",
        ),
        (
            "code",
            "/aas/oauth2/api/login/otp/verify",
            {"body": {"failed": "INVALID_OTP", **ESIA_MFA}},
            401,
            "bad_code",
        ),
        (
            "code",
            "/aas/oauth2/api/login/otp/verify",
            {
                "body": {
                    "failed": "INVALID_OTP",
                    "mfa_details": {"otp_details": {"verify_attempts_left": 0}},
                }
            },
            409,
            "login_blocked",
        ),
        (
            "code",
            "/aas/oauth2/api/login/otp/verify",
            {"status": 502, "body": b""},
            502,
            "upstream_error",
        ),
        ("captcha", "/captcha/api/public/v2/verify", {"body": {}}, 401, "bad_captcha"),
        (
            "captcha",
            "/aas/oauth2/api/anomaly/captcha/verify",
            {"body": {"failed": "WRONG"}},
            401,
            "bad_captcha",
        ),
        (
            "captcha",
            "/v3/auth/kauth/callback",
            {"status": 302, "body": b""},
            502,
            "upstream_format",
        ),
        (
            "captcha",
            "/aas/oauth2/api/anomaly/captcha/verify",
            {"body": {"action": "DONE", "redirect_url": "https://evil.example/cb"}},
            502,
            "upstream_format",
        ),
    ],
)
async def test_esia_login_keeps_secrets_out_of_log_on_every_outcome(
    app, routes, stage, path, answer, status, code
):
    routes.add(path, **answer)

    with captured_log() as stream:
        response, flow_ids = await esia_until(app, stage)

    assert (response.status_code, response.json()["error"]) == (status, code)
    for value in (PASSWORD, LOGIN, MFA_CODE, ANSWER):
        assert value not in response.text
    assert_no_credentials(stream.getvalue(), *flow_ids)


async def test_esia_success_keeps_secrets_out_of_log(app):
    with captured_log() as stream:
        response, flow_ids = await esia_until(app, "captcha")

    assert response.status_code == 200
    assert_no_credentials(stream.getvalue(), *flow_ids)


@pytest.mark.parametrize(
    ("stage", "code", "answer", "secret"),
    [
        ("code", "24a813", ANSWER, "24a813"),
        ("code", MFA_CODE * 10, ANSWER, MFA_CODE),
        ("captcha", MFA_CODE, [ANSWER], ANSWER),
        ("captcha", MFA_CODE, ANSWER * 50, ANSWER),
    ],
)
async def test_esia_bad_body_keeps_secrets_out_of_log_and_answer(app, stage, code, answer, secret):
    with captured_log() as stream:
        response, flow_ids = await esia_until(app, stage, code=code, answer=answer)

    assert (response.status_code, response.json()["error"]) == (400, "bad_request")
    assert secret not in response.text
    assert_no_credentials(stream.getvalue(), secret, *flow_ids)


async def test_esia_bad_start_body_keeps_password_out(app):
    transport = ASGITransport(app)
    with captured_log() as stream:
        async with AsyncClient(transport=transport, base_url="http://t", headers=AUTH_HEADERS) as c:
            response = await c.post("/v1/auth/esia", json={"login": LOGIN, "password": [PASSWORD]})

    assert response.status_code == 400
    assert PASSWORD not in response.text
    assert LOGIN not in response.text
    assert_no_credentials(stream.getvalue())


async def test_esia_flow_limit_keeps_secrets_out(app):
    # Лимит незаконченных входов (3 на потребителя): каждый старт оставляет
    # поток открытым, четвёртый упирается в него, а не в счётчик стартов.
    with captured_log() as stream:
        started = [(await esia_until(app, "start"))[0] for _ in range(3)]
        limited, _ = await esia_until(app, "start")

    assert [r.status_code for r in started] == [202] * 3
    assert limited.status_code == 429
    assert "незаконченных" in limited.json()["message"]
    assert_no_credentials(stream.getvalue())


async def test_esia_start_limit_keeps_secrets_out(app, routes):
    # Счётчик стартов (5 в минуту): старты кончаются отказом и потоков не
    # оставляют, поэтому шестой упирается именно в счётчик.
    routes.add("/aas/oauth2/api/login", {"failed": "INVALID"})

    with captured_log() as stream:
        refused = [(await esia_until(app, "start"))[0] for _ in range(5)]
        limited, _ = await esia_until(app, "start")

    assert [r.status_code for r in refused] == [401] * 5
    assert limited.status_code == 429
    assert "попыток входа" in limited.json()["message"]
    assert_no_credentials(stream.getvalue())


async def test_esia_expired_flow_keeps_secrets_out(app):
    with captured_log() as stream:
        transport = ASGITransport(app)
        async with AsyncClient(transport=transport, base_url="http://t", headers=AUTH_HEADERS) as c:
            expired = await c.post("/v1/auth/esia/no-such-flow/code", json={"code": MFA_CODE})

    assert expired.json()["error"] == "flow_expired"
    assert_no_credentials(stream.getvalue())


@pytest.mark.parametrize(
    "error",
    [UpstreamTimeout(), RuntimeError(f"упало на {LOGIN}:{PASSWORD}")],
)
async def test_esia_timeout_and_crash_keep_credentials_out_of_log(settings, error):
    app = create_app(settings, diary=core_diary(FakeDiary(esia_start=error)))
    transport = ASGITransport(app, raise_app_exceptions=False)

    with captured_log() as stream:
        async with AsyncClient(transport=transport, base_url="http://t", headers=AUTH_HEADERS) as c:
            response = await c.post("/v1/auth/esia", json=LOGIN_BODY)

    assert response.status_code in (500, 504)
    assert PASSWORD not in response.text
    assert_no_credentials(stream.getvalue())
