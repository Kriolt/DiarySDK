import dataclasses

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from diarysdk.server.app import create_app
from diarysdk.server.edge.ratelimit import RateLimiter
from tests.conftest import AUTH_HEADERS


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_burst_passes_then_next_request_waits():
    limiter = RateLimiter(rate=10, burst=30, clock=FakeClock())

    assert [limiter.acquire("bot") for _ in range(30)] == [None] * 30
    assert limiter.acquire("bot") == pytest.approx(0.1)


def test_tokens_refill_at_rate():
    clock = FakeClock()
    limiter = RateLimiter(rate=10, burst=30, clock=clock)
    for _ in range(30):
        limiter.acquire("bot")

    clock.now += 0.1

    assert limiter.acquire("bot") is None
    assert limiter.acquire("bot") is not None


def test_refill_is_capped_at_burst():
    clock = FakeClock()
    limiter = RateLimiter(rate=10, burst=30, clock=clock)
    limiter.acquire("bot")

    clock.now += 3600

    passed = sum(limiter.acquire("bot") is None for _ in range(40))
    assert passed == 30


def test_consumers_do_not_share_bucket():
    limiter = RateLimiter(rate=10, burst=1, clock=FakeClock())

    assert limiter.acquire("bot") is None
    assert limiter.acquire("bot") is not None
    assert limiter.acquire("site") is None


router = APIRouter()


@router.get("/ping")
async def ping():
    return {"ok": True}


async def test_v1_answers_429_with_retry_after(settings):
    app = create_app(
        dataclasses.replace(settings, rate_per_second=0.5, rate_burst=2), routers=[router]
    )
    transport = ASGITransport(app)
    async with AsyncClient(
        transport=transport, base_url="http://t", headers=AUTH_HEADERS
    ) as client:
        codes = [(await client.get("/v1/ping")).status_code for _ in range(2)]
        limited = await client.get("/v1/ping")

    assert codes == [200, 200]
    assert limited.status_code == 429
    assert limited.json()["error"] == "rate_limited"
    assert limited.headers["Retry-After"] == "2"
