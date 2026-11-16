import asyncio

import pytest

from diarysdk._context import ContextCache
from diarysdk.errors import UpstreamError
from tests.fakes import STUDENT


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Resolver:
    def __init__(self, *, delay=0.0, fail_first=False):
        self.calls = []
        self.delay = delay
        self.fail_first = fail_first

    async def __call__(self, token):
        self.calls.append(token)
        await asyncio.sleep(self.delay)
        if self.fail_first and len(self.calls) == 1:
            raise UpstreamError(upstream_status=503)
        return STUDENT


async def test_context_is_cached_for_ten_minutes():
    clock, resolve = FakeClock(), Resolver()
    cache = ContextCache(resolve, clock=clock)

    assert await cache.get("token-a") == STUDENT
    clock.now = 599
    await cache.get("token-a")
    assert resolve.calls == ["token-a"]

    clock.now = 601
    await cache.get("token-a")
    assert resolve.calls == ["token-a", "token-a"]


async def test_least_recently_used_token_is_evicted():
    resolve = Resolver()
    cache = ContextCache(resolve, maxsize=2, clock=FakeClock())

    await cache.get("a")
    await cache.get("b")
    await cache.get("a")  # a теперь свежее b
    await cache.get("c")  # вытесняет b
    await cache.get("a")
    await cache.get("b")

    assert resolve.calls == ["a", "b", "c", "b"]


async def test_concurrent_requests_share_one_profile_request():
    resolve = Resolver(delay=0.05)
    cache = ContextCache(resolve, clock=FakeClock())

    results = await asyncio.gather(*(cache.get("token-a") for _ in range(10)))

    assert results == [STUDENT] * 10
    assert resolve.calls == ["token-a"]


async def test_failure_is_shared_but_not_cached():
    resolve = Resolver(fail_first=True)
    cache = ContextCache(resolve, clock=FakeClock())

    with pytest.raises(UpstreamError):
        await cache.get("token-a")

    assert await cache.get("token-a") == STUDENT
    assert len(resolve.calls) == 2


async def test_cancelled_waiter_does_not_cancel_shared_request():
    resolve = Resolver(delay=0.05)
    cache = ContextCache(resolve, clock=FakeClock())

    impatient = asyncio.create_task(cache.get("token-a"))
    patient = asyncio.create_task(cache.get("token-a"))
    await asyncio.sleep(0.01)
    impatient.cancel()

    assert await patient == STUDENT
    assert resolve.calls == ["token-a"]


async def test_evicted_token_is_resolved_again():
    resolve = Resolver()
    cache = ContextCache(resolve, clock=FakeClock())
    await cache.get("token-a")

    cache.evict("token-a")
    await cache.get("token-a")

    assert resolve.calls == ["token-a", "token-a"]


async def test_token_itself_is_not_kept():
    cache = ContextCache(Resolver(), clock=FakeClock())

    await cache.get("secret.token.value")

    assert "secret.token.value" not in repr(vars(cache))
