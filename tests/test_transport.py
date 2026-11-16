import asyncio
import logging
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from diarysdk import _metrics, _transport
from diarysdk._transport import FlowCookies, RatingOff, Transport, call_name
from diarysdk.errors import NotFound, TokenInvalid, UpstreamError, UpstreamTimeout

PERSONAL = '{"type": "Ошибка", "description": "Иванов Иван, СНИЛС 123-456-789 01"}'
HOST = "https://diary.test"
SESSION_VALUE = "чужая-сессия-ученика".encode().hex()


def _json(data, status=200, headers=None):
    return httpx.Response(status, json=data, headers=headers)


class Diary:
    """Подставной дневник на MockTransport: считает обращения и одновременные запросы."""

    def __init__(self):
        self.url = HOST
        self.hits = {}
        self.active = 0
        self.max_active = 0
        self.requests = []
        self.network_failure = None

    def client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def hit(self, request):
        path = request.url.path
        self.hits[path] = self.hits.get(path, 0) + 1
        return self.hits[path]

    async def handle(self, request):
        self.requests.append(request)
        path = request.url.path
        self.hit(request)
        if request.url.host == "evil.test":
            return _json({"ok": True})
        if self.network_failure is not None and path == "/down":
            raise self.network_failure
        if path == "/echo":
            # Имена как на проводе: dict(request.headers) у httpx их понижает.
            raw = {key.decode(): value.decode() for key, value in request.headers.raw}
            return _json({"headers": raw, "query": dict(request.url.params)})
        if path.startswith("/status/"):
            return httpx.Response(
                int(path.rsplit("/", 1)[1]),
                text=PERSONAL,
                headers={"Content-Type": "application/json"},
            )
        if path == "/flaky":
            if self.hits[path] == 1:
                return httpx.Response(503, text="перегружен")
            return _json({"ok": True})
        if path == "/slow":
            await asyncio.sleep(2)
            return _json({"ok": True})
        if path == "/busy":
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.05)
            self.active -= 1
            return _json({"ok": True})
        if path == "/api/ej/rating/v1/rank/class":
            return _json({"message": "Рейтинг не доступен"})
        if path == "/to-evil":
            return httpx.Response(302, headers={"Location": "https://evil.test/steal?x=1"})
        if path == "/to-evil-307":
            return httpx.Response(307, headers={"Location": "https://evil.test/steal"})
        if path == "/to-http":
            return httpx.Response(302, headers={"Location": "http://diary.test/plain"})
        if path == "/to-echo-303":
            return httpx.Response(303, headers={"Location": "/echo"})
        if path == "/loop":
            return httpx.Response(302, headers={"Location": "/loop"})
        if path == "/plain":
            return _json({"ok": True})
        if path == "/big":
            return httpx.Response(200, content=b"x" * 5000)
        if path == "/big-stream":
            return httpx.Response(200, content=_chunks(b"x" * 2000, 10))
        if path == "/set-cookie":
            return _json(
                {"cookie": request.headers.get("Cookie")},
                headers={"Set-Cookie": f"session={SESSION_VALUE}; Path=/"},
            )
        if path == "/callback":
            # Как callback входа: кука и переадресация на страницу сайта.
            return httpx.Response(
                302,
                headers={"Location": "/echo", "Set-Cookie": "aupd_token=jwt-from-cookie; Path=/"},
            )
        if path == "/delete-cookie":
            # Так сервер стирает куку: пустое значение и Max-Age=0 или прошедший Expires.
            return httpx.Response(
                200,
                text="ok",
                headers=httpx.Headers(
                    [
                        ("Set-Cookie", "aupd_token=; Max-Age=0; Path=/"),
                        (
                            "Set-Cookie",
                            "session=old; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/",
                        ),
                        ("Set-Cookie", "kept=value; Path=/"),
                    ]
                ),
            )
        return httpx.Response(404)


async def _chunks(data, count):
    size = len(data) // count
    for index in range(count):
        yield data[index * size : (index + 1) * size]


@pytest.fixture
def diary():
    return Diary()


@pytest.fixture
def records():
    return []


@pytest.fixture
async def transport(diary, records):
    transport = Transport(
        user_agent="DiarySDK/test", retry_pause=0.01, recorder=records.append, http=diary.client()
    )
    async with transport as t:
        yield t


async def test_ok_response_is_returned(transport, diary):
    response = await transport.send("GET", f"{diary.url}/echo", headers={}, params={"a": "1"})

    assert response.status == 200
    assert response.content_type == "application/json"
    assert response.json()["query"] == {"a": "1"}


async def test_user_agent_and_encoding_are_ours(transport, diary):
    response = await transport.send(
        "GET",
        f"{diary.url}/echo",
        headers={"User-Agent": "Mozilla/5.0 случайный", "Accept-Encoding": "gzip, deflate, br"},
    )

    headers = response.json()["headers"]
    assert headers["User-Agent"] == "DiarySDK/test"
    # br без доп. пакета httpx не раскодирует — его не просим.
    assert headers["Accept-Encoding"] == "gzip, deflate"


@pytest.mark.parametrize(
    ("code", "error", "status"),
    [
        (400, UpstreamError, 400),
        (401, TokenInvalid, 401),
        (403, TokenInvalid, 403),
        (404, NotFound, None),
        (500, UpstreamError, 500),
    ],
)
async def test_error_status_becomes_diary_error(transport, diary, code, error, status):
    with pytest.raises(error) as info:
        await transport.send("GET", f"{diary.url}/status/{code}", headers={})

    if status is not None:
        shown = info.value.status if error is TokenInvalid else info.value.upstream_status
        assert shown == status
    # Тело ошибки дневника дальше транспорта не идёт: в нём бывают ПДн.
    assert "Иванов" not in str(info.value)
    assert "Иванов" not in repr(info.value)


async def test_500_is_not_retried(transport, diary, records):
    with pytest.raises(UpstreamError):
        await transport.send("GET", f"{diary.url}/status/500", headers={})

    assert diary.hits["/status/500"] == 1


async def test_get_is_retried_once_after_503(transport, diary, records):
    response = await transport.send("GET", f"{diary.url}/flaky", headers={})

    assert response.status == 200
    assert diary.hits["/flaky"] == 2
    assert records[-1].attempts == 2


async def test_second_503_is_final(transport, diary):
    with pytest.raises(UpstreamError) as info:
        await transport.send("GET", f"{diary.url}/status/503", headers={})

    assert info.value.upstream_status == 503
    assert diary.hits["/status/503"] == 2


async def test_post_is_not_retried(transport, diary):
    with pytest.raises(UpstreamError):
        await transport.send("POST", f"{diary.url}/status/503", headers={})

    assert diary.hits["/status/503"] == 1


@pytest.mark.parametrize("code", [502, 504])
async def test_put_is_attempted_once_on_gateway_errors(transport, diary, code):
    with pytest.raises(UpstreamError):
        await transport.send("PUT", f"{diary.url}/status/{code}", headers={}, json={"a": 1})

    assert diary.hits[f"/status/{code}"] == 1


async def test_network_error_is_retried_then_unavailable(transport, diary, records):
    diary.network_failure = httpx.ConnectError("отказ")

    with pytest.raises(UpstreamError) as info:
        await transport.send("GET", f"{diary.url}/down", headers={})

    assert info.value.upstream_status is None
    assert diary.hits["/down"] == 2
    assert records[-1].attempts == 2
    # Что именно не так с сетью (например, сертификат), без текста ошибки.
    assert records[-1].cause == "ConnectError"
    assert "отказ" not in repr(records[-1])


async def test_network_error_is_not_retried_for_post(transport, diary):
    diary.network_failure = httpx.ReadError("обрыв")

    with pytest.raises(UpstreamError):
        await transport.send("POST", f"{diary.url}/down", headers={}, json={})

    assert diary.hits["/down"] == 1


async def test_connect_timeout_is_timeout_and_retried_for_get(transport, diary, records):
    diary.network_failure = httpx.ConnectTimeout("долго")

    with pytest.raises(UpstreamTimeout):
        await transport.send("GET", f"{diary.url}/down", headers={})

    assert diary.hits["/down"] == 2
    assert records[-1].cause == "ConnectTimeout"


async def test_retry_pause_is_half_a_second_by_default(diary, monkeypatch):
    pauses = []

    async def fake_sleep(seconds):
        pauses.append(seconds)

    monkeypatch.setattr(_transport.asyncio, "sleep", fake_sleep)
    async with Transport(user_agent="t", http=diary.client()) as transport:
        response = await transport.send("GET", f"{diary.url}/flaky", headers={})

    assert response.status == 200
    assert pauses == [0.5]


async def test_slow_answer_is_timeout_without_retry(diary, records):
    async with Transport(
        user_agent="t", total_timeout=0.2, recorder=records.append, http=diary.client()
    ) as transport:
        with pytest.raises(UpstreamTimeout):
            await transport.send("GET", f"{diary.url}/slow", headers={})

    assert diary.hits["/slow"] == 1


async def test_concurrency_is_limited_for_whole_transport(diary):
    async with Transport(user_agent="t", concurrency=2, http=diary.client()) as transport:
        await asyncio.gather(
            *(transport.send("GET", f"{diary.url}/busy", headers={}) for _ in range(6))
        )

    assert diary.max_active == 2


async def test_rating_disabled_is_recognized_before_parsing(transport, diary):
    with pytest.raises(RatingOff):
        await transport.send("GET", f"{diary.url}/api/ej/rating/v1/rank/class", headers={})


async def test_cookies_are_not_shared_between_requests(transport, diary):
    await transport.send("GET", f"{diary.url}/set-cookie", headers={})
    second = await transport.send("GET", f"{diary.url}/set-cookie", headers={})

    assert second.json()["cookie"] is None


async def test_recorder_gets_final_response_even_on_error(transport, diary, records):
    token = call_name.set("rating.class")
    try:
        with pytest.raises(NotFound):
            await transport.send("GET", f"{diary.url}/status/404", headers={})
    finally:
        call_name.reset(token)

    [record] = records
    assert record.call == "rating.class"
    assert record.status == 404
    assert record.content_type == "application/json"
    assert record.body == PERSONAL.encode()
    assert record.attempts == 1


async def test_log_names_call_without_url_or_body(transport, diary, caplog):
    with caplog.at_level(logging.INFO, logger="diarysdk.transport"):
        with pytest.raises(UpstreamError):
            await transport.send("GET", f"{diary.url}/status/500", headers={}, call="marks")

    [record] = [r for r in caplog.records if r.getMessage() == "diary_call"]
    assert record.call == "marks"
    assert record.status == 500
    assert record.attempts == 1
    assert record.duration_ms >= 0
    assert "/status/500" not in caplog.text
    assert "diary.test" not in caplog.text
    assert "Иванов" not in caplog.text


async def test_each_attempt_counts_as_diary_call(transport, diary):
    counter = [0]
    token = _metrics.diary_calls.set(counter)
    try:
        await transport.send("GET", f"{diary.url}/flaky", headers={})
    finally:
        _metrics.diary_calls.reset(token)

    assert counter == [2]


async def test_redirect_is_followed_by_default(transport, diary):
    response = await transport.send("GET", f"{diary.url}/callback", headers={})

    assert response.status == 200
    assert diary.hits["/echo"] == 1


async def test_redirect_can_be_kept_with_its_cookies(transport, diary):
    response = await transport.send(
        "GET", f"{diary.url}/callback", headers={}, follow_redirects=False
    )

    assert response.status == 302
    assert response.location == "/echo"
    assert response.cookies == {"aupd_token": "jwt-from-cookie"}
    assert "/echo" not in diary.hits
    # Кука ответа — это токен: в repr ей не место.
    assert "jwt-from-cookie" not in repr(response)


async def test_cookies_of_response_do_not_reach_next_request(transport, diary):
    await transport.send("GET", f"{diary.url}/callback", headers={}, follow_redirects=False)
    second = await transport.send("GET", f"{diary.url}/set-cookie", headers={})

    assert second.json()["cookie"] is None


async def test_body_can_be_kept_out_of_record(transport, diary, records):
    with pytest.raises(NotFound):
        await transport.send("GET", f"{diary.url}/status/404", headers={}, record_body=False)

    [record] = records
    assert record.status == 404
    assert record.body == b""


async def test_get_retry_can_be_turned_off(transport, diary, records):
    # Шаги входа одноразовые: повтор GET с тем же кодом не нужен.
    with pytest.raises(UpstreamError):
        await transport.send("GET", f"{diary.url}/status/503", headers={}, retry=False)

    assert diary.hits["/status/503"] == 1
    assert records[-1].attempts == 1


async def test_status_can_be_returned_unchecked(transport, diary):
    # ЕСИА отвечает на неверный пароль телом с failed — его надо прочитать,
    # а не потерять в TokenInvalid.
    response = await transport.send(
        "POST", f"{diary.url}/status/401", headers={}, check_status=False, retry=False
    )

    assert response.status == 401
    assert response.json()["type"] == "Ошибка"


async def test_deletion_cookie_is_not_a_cookie_of_response(transport, diary):
    response = await transport.send("GET", f"{diary.url}/delete-cookie", headers={})

    assert response.cookies == {"kept": "value"}


async def test_flow_cookies_go_with_next_request_of_the_same_flow(transport, diary):
    url = f"{diary.url}/set-cookie"
    flow, other = FlowCookies(), FlowCookies()

    first = await transport.send("GET", url, headers={}, cookies=flow)
    second = await transport.send("GET", url, headers={}, cookies=flow)
    foreign = await transport.send("GET", url, headers={}, cookies=other)
    shared = await transport.send("GET", url, headers={})

    assert first.json()["cookie"] is None
    assert second.json()["cookie"] == f"session={SESSION_VALUE}"
    # Куки потока — только ему: ни другому потоку, ни общей сессии.
    assert foreign.json()["cookie"] is None
    assert shared.json()["cookie"] is None


async def test_flow_cookies_are_kept_from_unfollowed_redirect(transport, diary):
    base = diary.url
    flow = FlowCookies()

    await transport.send(
        "GET", f"{base}/callback", headers={}, cookies=flow, follow_redirects=False
    )
    echo = await transport.send("GET", f"{base}/echo", headers={}, cookies=flow)

    assert echo.json()["headers"]["Cookie"].startswith("aupd_token=")


async def test_cleared_flow_cookies_send_nothing(transport, diary):
    url = f"{diary.url}/set-cookie"
    flow = FlowCookies()
    await transport.send("GET", url, headers={}, cookies=flow)

    flow.clear()
    again = await transport.send("GET", url, headers={}, cookies=flow)

    assert again.json()["cookie"] is None


async def test_flow_cookie_goes_only_to_its_host_and_hides_value_in_repr(transport, diary):
    flow = FlowCookies()
    await transport.send("GET", f"{diary.url}/set-cookie", headers={}, cookies=flow)

    assert flow.header("https://other.test/set-cookie") is None
    assert flow.header(f"{diary.url}/set-cookie") == f"session={SESSION_VALUE}"
    assert repr(flow) == "FlowCookies(1)"
    assert SESSION_VALUE not in repr(flow)


async def test_flow_cookie_deleted_by_expired_or_zero_max_age(transport, diary):
    flow = FlowCookies()
    flow._jar.set("aupd_token", "t", domain="diary.test", path="/")
    flow._jar.set("session", "s", domain="diary.test", path="/")

    await transport.send("GET", f"{diary.url}/delete-cookie", headers={}, cookies=flow)

    assert flow.header(f"{diary.url}/") == "kept=value"


async def test_cookie_with_future_expires_is_a_cookie_of_response():
    future = format_datetime(datetime.now(UTC) + timedelta(days=1), usegmt=True)

    def handler(request):
        return httpx.Response(200, headers={"Set-Cookie": f"a=1; Expires={future}"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with Transport(user_agent="t", http=http) as other:
        response = await other.send("GET", f"{HOST}/", headers={})

    assert response.cookies == {"a": "1"}


async def test_body_over_limit_is_cut_off(diary, records):
    async with Transport(
        user_agent="t", max_body=1000, recorder=records.append, http=diary.client()
    ) as transport:
        with pytest.raises(UpstreamError) as info:
            await transport.send("GET", f"{diary.url}/big", headers={})
        with pytest.raises(UpstreamError):
            await transport.send("GET", f"{diary.url}/big-stream", headers={}, retry=True)
        ok = await transport.send("GET", f"{diary.url}/echo", headers={})

    assert info.value.upstream_status is None
    assert records[0].cause == "BodyTooLarge"
    # Слишком большой ответ не повторяют.
    assert diary.hits["/big"] == 1
    assert ok.status == 200


async def test_body_at_limit_is_read(diary):
    async with Transport(user_agent="t", max_body=5000, http=diary.client()) as transport:
        response = await transport.send("GET", f"{diary.url}/big", headers={})

    assert len(response.body) == 5000


async def test_json_body_is_sent_as_before(transport, diary):
    await transport.send("PUT", f"{diary.url}/status/200", headers={}, json={"к": [1, 2]})

    [request] = diary.requests
    assert request.content == b'{"\\u043a": [1, 2]}'
    assert request.headers["Content-Type"] == "application/json"


async def test_redirect_is_not_followed_when_asked_for_a_write(transport, diary):
    response = await transport.send(
        "PUT", f"{diary.url}/callback", headers={}, follow_redirects=False
    )

    assert response.status == 302
    assert "/echo" not in diary.hits


async def test_injected_client_is_not_closed_by_transport(diary):
    http = diary.client()
    async with Transport(user_agent="t", http=http):
        pass

    assert not http.is_closed
    await http.aclose()


async def test_own_client_is_closed_and_verifies_tls():
    transport = Transport(user_agent="t")
    await transport.start()
    own = transport._http
    assert own is not None
    assert own.follow_redirects is False
    await transport.close()

    assert own.is_closed


async def test_client_cookie_jar_stays_empty(transport, diary):
    await transport.send("GET", f"{diary.url}/set-cookie", headers={})

    assert len(transport._http.cookies.jar) == 0


async def test_send_before_start_is_programming_error():
    with pytest.raises(RuntimeError):
        await Transport(user_agent="t").send("GET", f"{HOST}/", headers={})


async def test_httpx_does_not_log_our_requests(transport, diary, caplog):
    # На INFO httpx пишет полный URL запроса: в нём одноразовый код входа и ID.
    with caplog.at_level(logging.INFO):
        await transport.send("GET", f"{diary.url}/echo", headers={}, params={"code": "секрет-77"})

    assert "секрет-77" not in caplog.text
    assert not [r for r in caplog.records if r.name == "httpx"]


SECRET_HEADERS = {
    "Auth-Token": "diary-token-secret",
    "Authorization": "Bearer secret",
    "Profile-Id": "7001",
    "X-Custom-Token": "other-secret",
    "Accept": "application/json",
}


def _evil_requests(diary):
    return [r for r in diary.requests if r.url.host == "evil.test"]


async def test_cross_origin_redirect_does_not_carry_secrets(transport, diary):
    flow = FlowCookies()
    await transport.send("GET", f"{diary.url}/set-cookie", headers={}, cookies=flow)

    response = await transport.send(
        "GET", f"{diary.url}/to-evil", headers=SECRET_HEADERS, cookies=flow
    )

    assert response.status == 200
    [hop] = _evil_requests(diary)
    sent = {key.decode().lower() for key, _ in hop.headers.raw}
    assert not sent & {"auth-token", "authorization", "cookie", "profile-id", "x-custom-token"}
    assert hop.headers["User-Agent"] == "DiarySDK/test"
    assert hop.headers["Accept"] == "application/json"
    assert hop.url.query == b"x=1"


async def test_cross_origin_redirect_to_plain_http_does_not_carry_secrets(transport, diary):
    await transport.send("GET", f"{diary.url}/to-http", headers=SECRET_HEADERS)

    hop = diary.requests[-1]
    assert hop.url.scheme == "http"
    assert "auth-token" not in hop.headers
    assert "authorization" not in hop.headers


async def test_cross_origin_redirect_that_keeps_method_is_refused(transport, diary):
    with pytest.raises(UpstreamError):
        await transport.send(
            "POST", f"{diary.url}/to-evil-307", headers=SECRET_HEADERS, json={"a": 1}
        )

    assert _evil_requests(diary) == []


async def test_same_origin_redirect_keeps_headers(transport, diary):
    response = await transport.send(
        "GET", f"{diary.url}/callback", headers={"Auth-Token": "t", "X-Y": "z"}
    )

    sent = {key.lower(): value for key, value in response.json()["headers"].items()}
    assert sent["auth-token"] == "t"
    assert sent["x-y"] == "z"
    assert sent["user-agent"] == "DiarySDK/test"


async def test_see_other_turns_post_into_get_without_body(transport, diary):
    response = await transport.send(
        "POST", f"{diary.url}/to-echo-303", headers={"Auth-Token": "t"}, json={"a": 1}
    )

    assert response.status == 200
    assert diary.requests[-1].method == "GET"
    assert diary.requests[-1].content == b""
    assert "content-type" not in diary.requests[-1].headers


async def test_redirect_loop_is_an_upstream_error(transport, diary, records):
    with pytest.raises(UpstreamError):
        await transport.send("GET", f"{diary.url}/loop", headers={})

    assert records[-1].cause == "TooManyRedirects"
