"""Вход по логину и паролю портала: свои запросы через настоящий транспорт.

Портал — httpx.MockTransport. Последовательность: POST /lms/api/sessions,
затем callback с одноразовым кодом, токен — в куке aupd_token.
"""

import asyncio
import json
import logging

import httpx
import pytest

from diarysdk._hosts import Hosts
from diarysdk._login import password as login
from diarysdk._transport import Transport
from diarysdk.errors import BadCredentials, UpstreamError, UpstreamFormat, UpstreamTimeout
from tests.tokens import valid_token

LOGIN = "ivanov-login@example.test"
PASSWORD = "Пароль-секрет-42"
CODE = "one-time-code-77"
JWT = valid_token()
BASE = "https://portal.test"
GRAB = "https://grab.test"


def _json(data, status=200):
    return httpx.Response(status, json=data)


def _redirect(location, status=302, cookie=None):
    headers = httpx.Headers({"Location": location})
    if cookie is not None:
        headers["Set-Cookie"] = cookie
    return httpx.Response(status, headers=headers)


class Portal:
    """Подставной портал входа на MockTransport. mode — какой ответ дать."""

    def __init__(self):
        self.mode = "ok"
        self.sessions = []
        self.callbacks = []
        self.landing_hits = 0
        self.hops = []
        self.hop_cookies = []
        self.callback_cookies = []
        self.base = BASE
        self.hosts = Hosts(dnevnik=BASE, school_api=f"{BASE}/api", school=BASE)

    def client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    async def handle(self, request):
        path = request.url.path
        if request.method == "POST" and path == "/lms/api/sessions":
            return self.session(request)
        if request.method == "GET" and path == "/v3/auth/kauth/callback":
            self.callback_cookies.append(request.headers.get("Cookie"))
            return self.callback(request)
        if request.method == "GET" and path == "/":
            self.landing_hits += 1
            return httpx.Response(200, text="ok")
        if request.method == "GET" and path.startswith("/hop/"):
            self.hop_cookies.append(request.headers.get("Cookie"))
            return self.hop(int(path.rsplit("/", 1)[1]))
        if path == "/grab":
            # Чужой хост: на него sessions пытается переадресовать вход.
            self.grabbed.append({"method": request.method, "body": request.content.decode()})
            return _json({"authentication_token": CODE})
        return httpx.Response(404)

    def session(self, request):
        self.sessions.append(
            {"body": json.loads(request.content), "accept": request.headers["Accept"]}
        )
        match self.mode:
            case "wrong_password":
                return _json({"error": "Неверный логин или пароль"}, 401)
            case "forbidden":
                return _json({"error": "Доступ запрещён"}, 403)
            case "error_body":
                return _json({"errors": ["Неверный логин или пароль"]})
            case "no_code":
                return _json({"id": 1, "email": LOGIN})
            case "not_json":
                return httpx.Response(
                    200, text="<html>техработы</html>", headers={"Content-Type": "text/html"}
                )
            case "server_error":
                return httpx.Response(503, text="перегружен")
            case "not_found":
                return httpx.Response(404)
            case "bad_request" | "unprocessable":
                return _json(
                    {"error": "Некорректный запрос"}, 400 if self.mode == "bad_request" else 422
                )
            case "redirect_307" | "redirect_302":
                status = 307 if self.mode == "redirect_307" else 302
                return _redirect(f"{GRAB}/grab", status)
        # Ответ входа несёт контакты пользователя — их не должно быть в записи.
        return _json(
            {"id": 1, "email": LOGIN, "phone_number": "79990001122", "authentication_token": CODE}
        )

    def callback(self, request):
        self.callbacks.append(dict(request.url.params))
        if self.mode == "callback_refused":
            return httpx.Response(401)
        if self.mode == "callback_unavailable":
            return httpx.Response(503)
        if self.mode == "session_cookie_chain":
            # Куку сессии ставит сам callback; следующие шаги без неё токена не отдадут.
            return _redirect("/hop/1", cookie="sid=hop-session; Path=/")
        if self.mode in ("cookie_on_hop2", "chain_without_cookie", "loop"):
            return _redirect("/hop/1")
        if self.mode == "deleted_then_set":
            # Сначала портал стирает старую куку, настоящую ставит на шаге дальше.
            return _redirect("/hop/1", cookie="aupd_token=; Max-Age=0; Path=/")
        if self.mode == "foreign_host":
            return _redirect("https://evil.example/steal")
        if self.mode == "no_cookie":
            return _redirect("/")
        value = "not-a-jwt" if self.mode == "bad_jwt" else JWT
        return _redirect("/", cookie=f"aupd_token={value}; Path=/")

    def hop(self, n):
        self.hops.append(n)
        if self.mode == "loop":
            return _redirect("/hop/1")
        if n == 1 and self.mode == "session_cookie_chain":
            return _redirect(f"{self.base}/hop/2")
        if n == 1:
            # Второй шаг — абсолютным адресом того же хоста.
            return _redirect(f"{self.base}/hop/2")
        headers = {}
        if self.mode == "session_cookie_chain":
            if "sid=hop-session" not in (self.hop_cookies[-1] or ""):
                return httpx.Response(200, text="нужна сессия")
            if n == 2:
                headers["Set-Cookie"] = f"aupd_token={JWT}; Path=/"
        if self.mode in ("cookie_on_hop2", "deleted_then_set"):
            headers["Set-Cookie"] = f"aupd_token={JWT}; Path=/"
        return httpx.Response(200, text="ok", headers=headers)


@pytest.fixture
def portal():
    fake = Portal()
    fake.grabbed = []
    return fake


@pytest.fixture
def records():
    return []


@pytest.fixture
async def transport(portal, records):
    async with Transport(
        user_agent="DiarySDK/test", recorder=records.append, http=portal.client()
    ) as t:
        yield t


async def test_password_login_returns_token_from_cookie(portal, transport):
    token = await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert token == JWT
    assert portal.sessions == [
        {"body": {"login": LOGIN, "password_plain": PASSWORD}, "accept": "application/json"}
    ]
    assert portal.callbacks == [{"code": CODE}]
    # Переадресацию после callback не проходим: токен уже в куке.
    assert portal.landing_hits == 0


async def test_login_records_have_no_bodies_or_credentials(portal, transport, records):
    await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert [r.call for r in records] == ["login.password", "login.callback"]
    assert all(r.body == b"" for r in records)
    assert PASSWORD not in repr(records)
    assert LOGIN not in repr(records)


@pytest.mark.parametrize("mode", ["wrong_password", "forbidden", "error_body"])
async def test_refused_login_is_bad_credentials(portal, transport, mode):
    portal.mode = mode

    with pytest.raises(BadCredentials) as info:
        await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert portal.callbacks == []
    assert PASSWORD not in str(info.value)
    assert LOGIN not in str(info.value)


async def test_cookies_set_by_redirect_chain_are_sent_on_and_then_forgotten(portal, transport):
    portal.mode = "session_cookie_chain"

    token = await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert token == JWT
    # Куку сессии получил callback, и она ушла на оба следующих шага цепочки.
    assert portal.hop_cookies == ["sid=hop-session", "sid=hop-session"]
    # Банка стёрта после входа, общая банка транспорта кук не держит: второй вход
    # начинается с чистого листа и не получает куки первого.
    await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)
    assert portal.callback_cookies == [None, None]


async def test_token_cookie_on_later_redirect_hop_is_found(portal, transport, records):
    # Идём по переадресациям: кука может прийти не
    # на callback, а на шаге после него.
    portal.mode = "cookie_on_hop2"

    token = await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert token == JWT
    assert portal.hops == [1, 2]
    assert [r.call for r in records] == [
        "login.password",
        "login.callback",
        "login.redirect",
        "login.redirect",
    ]
    assert all(r.body == b"" and r.attempts == 1 for r in records)


async def test_deleting_token_cookie_does_not_stop_the_search(portal, transport):
    portal.mode = "deleted_then_set"

    token = await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert token == JWT
    assert portal.hops == [1, 2]


@pytest.mark.parametrize(
    ("url", "same"),
    [
        ("https://authedu.mosreg.ru:443/hop", True),
        ("HTTPS://AuthEdu.Mosreg.Ru/hop", True),
        ("http://authedu.mosreg.ru:80/hop", False),
        ("https://authedu.mosreg.ru:8443/hop", False),
        ("https://authedu.mosreg.ru.evil.example/hop", False),
        ("https://user@authedu.mosreg.ru/hop", False),
    ],
)
def test_origin_treats_default_port_as_same_host(url, same):
    assert (login.origin(url) == login.origin("https://authedu.mosreg.ru")) is same


async def test_redirect_chain_without_cookie_is_format_error(portal, transport):
    portal.mode = "chain_without_cookie"

    with pytest.raises(UpstreamFormat):
        await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert portal.hops == [1, 2]


async def test_redirect_to_foreign_host_is_not_followed(portal, transport, records):
    portal.mode = "foreign_host"

    with pytest.raises(UpstreamFormat) as info:
        await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    # Ни одного запроса на чужой хост: последний вызов — сам callback.
    assert records[-1].call == "login.callback"
    assert "evil.example" not in str(info.value)


async def test_redirect_loop_stops_after_five_hops(portal, transport):
    portal.mode = "loop"

    with pytest.raises(UpstreamFormat):
        await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert portal.hops == [1] * login.MAX_REDIRECTS


@pytest.mark.parametrize("mode", ["no_code", "not_json", "no_cookie", "bad_jwt"])
async def test_unexpected_answer_is_format_error_without_values(portal, transport, mode):
    portal.mode = mode

    with pytest.raises(UpstreamFormat) as info:
        await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    text = str(info.value) + repr(info.value.problems)
    for value in (PASSWORD, LOGIN, CODE, "not-a-jwt"):
        assert value not in text


@pytest.mark.parametrize("mode", ["redirect_307", "redirect_302"])
async def test_redirect_on_sessions_is_not_followed(portal, transport, mode):
    # 307/308 клиент с переходами повторил бы с тем же телом — логин и пароль ушли бы
    # чужому хосту. Любой 3xx на sessions — сбой формата, без перехода.
    portal.mode = mode

    with pytest.raises(UpstreamFormat) as info:
        await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert portal.grabbed == []
    assert portal.callbacks == []
    assert PASSWORD not in str(info.value)


async def test_server_error_is_not_retried(portal, transport):
    portal.mode = "server_error"

    with pytest.raises(UpstreamError) as info:
        await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert info.value.upstream_status == 503
    # Шаги входа — POST: после сбоя потребитель начинает вход заново.
    assert len(portal.sessions) == 1


@pytest.mark.parametrize(("mode", "status"), [("bad_request", 400), ("unprocessable", 422)])
async def test_portal_400_and_422_on_sessions_are_upstream_error(portal, transport, mode, status):
    # R10: отказ формата запроса — не «неверный пароль» и не поломка формата
    # ответа: потребитель видит upstream_error, а не bad_credentials.
    portal.mode = mode

    with pytest.raises(UpstreamError) as info:
        await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert info.value.upstream_status == status
    assert len(portal.sessions) == 1
    assert portal.callbacks == []
    assert PASSWORD not in str(info.value)


async def test_failed_callback_is_not_retried(portal, transport):
    portal.mode = "callback_unavailable"

    with pytest.raises(UpstreamError) as info:
        await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert info.value.upstream_status == 503
    assert len(portal.callbacks) == 1


@pytest.mark.parametrize(("mode", "status"), [("not_found", 404), ("callback_refused", 401)])
async def test_other_refusals_are_upstream_errors(portal, transport, mode, status):
    # 404 и отказ callback — не «нет ученика» и не «плохой токен»: у
    # потребителя ещё нет токена, а код мы получили только что.
    portal.mode = mode

    with pytest.raises(UpstreamError) as info:
        await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert info.value.upstream_status == status


async def test_network_error_is_unavailable(portal, records):
    def refuse(request):
        raise httpx.ConnectError("отказ")

    http = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    async with Transport(user_agent="t", recorder=records.append, http=http) as transport:
        with pytest.raises(UpstreamError) as info:
            await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    assert info.value.upstream_status is None
    # Первый шаг входа — POST: без повтора.
    assert [r.attempts for r in records] == [1]


async def test_slow_portal_is_timeout(portal):
    async def slow(request):
        await asyncio.sleep(1)
        return _json({})

    http = httpx.AsyncClient(transport=httpx.MockTransport(slow))
    async with Transport(user_agent="t", total_timeout=0.1, http=http) as transport:
        with pytest.raises(UpstreamTimeout):
            await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)


async def test_log_has_no_credentials(portal, transport, caplog):
    with caplog.at_level(logging.DEBUG):
        await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)
        portal.mode = "wrong_password"
        with pytest.raises(BadCredentials):
            await login.password_login(transport, portal.hosts, LOGIN, PASSWORD)

    # Пишут и httpx с httpcore (в них URL и заголовки запросов): проверяем всё.
    ours = caplog.records
    assert any(r.name == "diarysdk.transport" for r in ours)
    # Вместе с полями extra: в них call, status, cause.
    text = "\n".join(f"{r.getMessage()} {vars(r)}" for r in ours)
    for value in (PASSWORD, LOGIN, CODE, JWT):
        assert value not in text
