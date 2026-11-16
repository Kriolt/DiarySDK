"""Хранилище потоков входа через ЕСИА: срок, лимиты, привязка к потребителю, закрытие."""

import asyncio
import contextlib
import logging
import re
from datetime import UTC, datetime, timedelta

import pytest

from diarysdk.errors import FlowExpired, RateLimited, retry_after_header
from diarysdk.server.services.login_flows import SWEEP_INTERVAL, LoginFlows, sweep_forever

START = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


class FakeLogin:
    """Вместо LoginFlow ядра: реестру нужны только срок и закрытие."""

    def __init__(self, expires_at):
        self.expires_at = expires_at
        self.closed = 0

    async def close(self):
        self.closed += 1


def touch(flow, clock):
    """Шаг входа продлевает срок: это делает сам LoginFlow."""
    flow.login.expires_at = clock.now + timedelta(minutes=5)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def flows(clock):
    return LoginFlows(now=clock)


async def opened(flows, consumer="bot"):
    flow = await flows.reserve(consumer)
    session = FakeLogin(flows._now() + timedelta(minutes=5))
    await flows.activate(flow, session)
    return flow, session


def assert_expired(error):
    assert (error.http_status, error.code) == (404, "flow_expired")


async def test_flow_id_is_128_random_bits_url_safe(flows):
    ids = {(await opened(flows, f"c{i}"))[0].flow_id for i in range(20)}

    assert len(ids) == 20
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{22}", flow_id) for flow_id in ids)


async def test_open_flow_is_found_by_its_consumer(flows):
    flow, _ = await opened(flows)

    assert await flows.find("bot", flow.flow_id) is flow


async def test_reserved_flow_is_not_found_until_activated(flows):
    flow = await flows.reserve("bot")

    with pytest.raises(FlowExpired) as info:
        await flows.find("bot", flow.flow_id)

    assert_expired(info.value)


@pytest.mark.parametrize("consumer", ["site", "bot2", ""])
async def test_foreign_flow_looks_like_expired(flows, consumer):
    flow, session = await opened(flows)

    with pytest.raises(FlowExpired) as foreign:
        await flows.find(consumer, flow.flow_id)
    with pytest.raises(FlowExpired) as unknown:
        await flows.find("bot", "no-such-flow")

    assert_expired(foreign.value)
    # Чужой поток не отличить от несуществующего: тот же ответ.
    assert foreign.value.message == unknown.value.message
    # И чужой запрос поток не трогает.
    assert await flows.find("bot", flow.flow_id) is flow
    assert session.closed == 0


async def test_flow_expires_five_minutes_after_last_step(flows, clock):
    flow, session = await opened(flows)
    assert flow.expires_at == START + timedelta(minutes=5)

    clock.advance(minutes=4)
    touch(flow, clock)
    clock.advance(minutes=4)
    assert await flows.find("bot", flow.flow_id) is flow

    clock.advance(minutes=1, seconds=1)
    with pytest.raises(FlowExpired) as info:
        await flows.find("bot", flow.flow_id)

    assert_expired(info.value)
    assert session.closed == 1
    assert len(flows) == 0


async def test_three_flows_per_consumer_then_rate_limited(flows, clock):
    for _ in range(3):
        await opened(flows)
        clock.advance(seconds=30)

    with pytest.raises(RateLimited) as info:
        await flows.reserve("bot")

    assert (info.value.http_status, info.value.code) == (429, "rate_limited")
    # Место освободится, когда истечёт старший поток: 5 мин − 90 с.
    assert retry_after_header(info.value) == "210"
    # Другому потребителю место есть.
    assert (await flows.reserve("site")).consumer == "site"


async def test_reserved_flows_count_against_the_limit(flows):
    for _ in range(3):
        await flows.reserve("bot")

    with pytest.raises(RateLimited):
        await flows.reserve("bot")


async def test_hundred_flows_in_total(clock):
    flows = LoginFlows(now=clock)
    for i in range(100):
        await opened(flows, f"c{i // 3}")

    with pytest.raises(RateLimited) as info:
        await flows.reserve("newcomer")

    assert (info.value.http_status, info.value.code) == (429, "rate_limited")
    assert retry_after_header(info.value) == "300"


async def test_expired_flows_free_their_place(flows, clock):
    sessions = [(await opened(flows))[1] for _ in range(3)]

    clock.advance(minutes=5)
    await flows.reserve("bot")

    assert [s.closed for s in sessions] == [1, 1, 1]


async def test_drop_closes_session_once_and_forgets_flow(flows):
    flow, session = await opened(flows)

    await flows.drop(flow)
    await flows.drop(flow)

    assert session.closed == 1
    assert not flows.is_open(flow)
    with pytest.raises(FlowExpired):
        await flows.find("bot", flow.flow_id)


async def test_dropping_reserved_flow_frees_place(flows):
    flow = await flows.reserve("bot")
    await flows.drop(flow)

    for _ in range(3):
        await flows.reserve("bot")


async def test_busy_flow_is_not_swept(flows, clock):
    flow, session = await opened(flows)

    async with flow.lock:
        clock.advance(minutes=6)
        await flows.reserve("site")
        # Шаг ещё идёт: куки ему нужны до конца. Просрочку увидит сам LoginFlow.
        assert session.closed == 0
        assert await flows.find("bot", flow.flow_id) is flow

    await flows.reserve("site")
    assert session.closed == 1


async def test_close_all_closes_every_session(flows):
    sessions = [(await opened(flows, f"c{i}"))[1] for i in range(3)]

    await flows.close_all()

    assert [s.closed for s in sessions] == [1, 1, 1]
    assert len(flows) == 0


# --- Уборка по таймеру: без единого запроса входа ---


async def test_sweep_closes_expired_flow_without_any_request(flows, clock):
    flow, session = await opened(flows)
    fresh, kept = await opened(flows, "site")
    clock.advance(minutes=4)
    touch(fresh, clock)

    clock.advance(minutes=1, seconds=1)
    await flows.sweep()

    assert session.closed == 1
    assert not flows.is_open(flow)
    assert kept.closed == 0 and flows.is_open(fresh)


async def test_sweep_skips_busy_flow(flows, clock):
    flow, session = await opened(flows)

    async with flow.lock:
        clock.advance(minutes=6)
        await flows.sweep()
        assert session.closed == 0

    await flows.sweep()
    assert session.closed == 1


class Ticking:
    """Уборка с сигналом: тест ждёт события, а не угадывает время сном."""

    def __init__(self, inner=None, *, ticks=1):
        self.inner = inner
        self.ticks = ticks
        self.calls = 0
        self.done = asyncio.Event()

    async def sweep(self):
        self.calls += 1
        if self.calls >= self.ticks:
            self.done.set()
        if self.inner is not None:
            await self.inner.sweep()


async def run_sweeper(target):
    """Уборщик с нулевым интервалом, пока target не просигналит."""
    task = asyncio.create_task(sweep_forever(target, interval=0))
    try:
        await asyncio.wait_for(target.done.wait(), timeout=5)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_sweeper_tick_closes_expired_flows(flows, clock):
    _, session = await opened(flows)
    clock.advance(minutes=5, seconds=1)

    await run_sweeper(Ticking(flows))

    assert session.closed == 1
    assert len(flows) == 0


class Broken(Ticking):
    async def sweep(self):
        await super().sweep()
        raise RuntimeError("упало на Пароль-секрет-42")


async def test_sweeper_survives_errors_and_logs_type_only(caplog):
    broken = Broken(ticks=3)

    with caplog.at_level(logging.DEBUG):
        await run_sweeper(broken)

    assert broken.calls >= 3
    ours = [r for r in caplog.records if r.name.startswith("diarysdk")]
    assert ours and all(r.error_type == "RuntimeError" for r in ours)
    text = "\n".join(f"{r.getMessage()} {vars(r)}" for r in ours)
    assert "Пароль-секрет-42" not in text
    assert all(r.exc_info is None for r in ours)


async def test_sweep_interval_is_thirty_seconds():
    # Худший срок жизни брошенного потока — TTL + интервал (README).
    assert SWEEP_INTERVAL == 30.0


async def test_activate_on_dropped_flow_closes_session_and_says_expired(flows):
    flow = await flows.reserve("bot")
    await flows.drop(flow)
    session = FakeLogin(START)

    with pytest.raises(FlowExpired) as info:
        await flows.activate(flow, session)

    assert_expired(info.value)
    assert session.closed == 1
    assert flow.login is None and len(flows) == 0
