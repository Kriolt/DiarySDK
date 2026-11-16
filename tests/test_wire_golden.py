"""Запросы на проводе: каждый запрос из золотых снимков идёт через настоящий
Transport в httpx.MockTransport, и перехваченный httpx.Request сверяется с
tests/golden/reads.json и writes.json. Так закреплены имена заголовков,
Auth-Token, User-Agent, Accept-Encoding, Content-Type, параметры и тело на
реальном пути отправки (в test_golden до транспорта запрос не доходит).
"""

import json
from urllib.parse import urlsplit

import httpx
import pytest

from diarysdk._gateway import DiaryGateway
from diarysdk._transport import Transport
from tests.fakes import DIARY_TOKEN, HOSTS
from tests.test_golden import GOLDEN, READS, TODAY, WRITES, Call, _fake

USER_AGENT = "DiarySDK/wire-test"
# Их на проводе добавляет httpx сам, в снимке им делать нечего.
ADDED_BY_HTTPX = {"host", "content-length"}
HIDDEN = {"authorization", "cookie", "user-agent"}


def _snapshot(request: httpx.Request) -> dict:
    url = urlsplit(str(request.url))
    headers = {key.decode().lower(): value.decode() for key, value in request.headers.raw}
    return {
        "method": request.method,
        "url": f"{url.scheme}://{url.netloc}{url.path}",
        "params": dict(sorted(request.url.params.items())),
        "headers": headers,
        "json": json.loads(request.content) if request.content else None,
    }


def _like_golden(wire: dict, golden: dict) -> dict:
    """Приводит снимок провода к виду эталона: то, что транспорт добавляет
    сам, проверяется отдельно и из сравнения убирается."""
    headers = dict(wire["headers"])
    assert headers.pop("user-agent") == USER_AGENT
    # Постоянный набор кодировок вместо библиотечного «gzip, deflate, br».
    assert headers["accept-encoding"] == "gzip, deflate"
    if wire["json"] is not None:
        assert headers["content-type"] == "application/json"
    auth = "authorization" in headers
    for name in ADDED_BY_HTTPX | HIDDEN:
        headers.pop(name, None)
    for name in ("accept", "accept-encoding", "connection", "content-type"):
        if name not in golden["headers"]:
            headers.pop(name, None)
    if "accept-encoding" in headers:
        headers["accept-encoding"] = golden["headers"]["accept-encoding"]
    result = {**wire, "headers": dict(sorted(headers.items()))}
    if auth:
        result["auth"] = True
    return result


async def _wire(call: Call) -> list[dict]:
    fake = _fake()
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        route = next(
            (
                fake.routes[key]
                for key in (f"{request.method} {request.url.path}", request.url.path)
                if key in fake.routes
            ),
            None,
        )
        assert route is not None, f"подставной дневник не знает путь {request.url.path}"
        return httpx.Response(
            route.status, content=route.body, headers={"Content-Type": route.content_type or ""}
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    try:
        async with Transport(user_agent=USER_AGENT, http=http) as transport:
            await call(DiaryGateway(transport, HOSTS, today=lambda: TODAY))
    finally:
        await http.aclose()
    return [_snapshot(request) for request in seen]


def _golden(name: str) -> dict:
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", READS)
async def test_read_on_the_wire_matches_golden(name):
    expected = _golden("reads")[name]

    wire = await _wire(READS[name])

    assert [_like_golden(w, g) for w, g in zip(wire, expected, strict=True)] == expected


@pytest.mark.parametrize("name", WRITES)
async def test_write_on_the_wire_matches_golden(name):
    expected = _golden("writes")[name]

    wire = await _wire(WRITES[name])

    assert [_like_golden(w, g) for w, g in zip(wire, expected, strict=True)] == expected


async def test_token_goes_in_auth_headers_on_the_wire():
    [request] = await _wire(READS["marks"])

    assert request["headers"]["auth-token"] == DIARY_TOKEN
    assert DIARY_TOKEN in request["headers"]["authorization"]
