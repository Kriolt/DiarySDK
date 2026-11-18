"""Ознакомление родителя с дневником: чтение отметок и отметка недели."""

import json
import re
from datetime import date

import httpx
import pytest

from diarysdk import _clock as clock
from diarysdk import errors
from tests.test_client import DiaryServer, now, token  # noqa: F401 - фикстуры
from tests.test_parent import parent_profile

ACKS = "/api/ej/core/family/v1/aware_journals"
ACK = {
    "id": 1,
    "created_at": "03.02.2026 10:15",
    "updated_at": "03.02.2026 10:15",
    "parent_profile_id": 7001,
    "student_profile_id": 9001,
    "date": "2026-02-03",
    "week": "2026-02-02",
}


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(clock, "today_msk", lambda: date(2026, 2, 4))  # среда
    server = DiaryServer()
    server.fake.add("/api/family/web/v1/profile", parent_profile())
    server.fake.add(f"GET {ACKS}", [])
    server.fake.add(f"POST {ACKS}", {"id": 2})
    return server


@pytest.fixture
async def parent(server, now, token):  # noqa: F811
    async with server.diary() as diary:
        yield diary.parent(token)


def _sent(server, method):
    return [r for r in server.requests if r.method == method and r.url.path == ACKS]


async def test_journal_acks_are_mapped_and_asked_for_the_child(parent, server):
    server.fake.add(f"GET {ACKS}", [ACK])

    acks = await parent.journal_acks(9001, date(2026, 2, 4), date(2026, 2, 8))

    assert [(a.week, a.child_id) for a in acks] == [(date(2026, 2, 2), 9001)]
    assert acks[0].created_at.isoformat().startswith("2026-02-03T10:15")
    request = _sent(server, "GET")[0]
    assert dict(request.url.params) == {
        "week_from": "2026-02-02",
        "week_to": "2026-02-08",
        "student_profile_ids": "9001",
    }
    assert request.headers["profile-type"] == "parent"
    assert request.headers["profile-id"] == "7001"


async def test_journal_acks_default_to_current_week(parent, server):
    await parent.journal_acks(9001)

    params = dict(_sent(server, "GET")[0].url.params)
    assert (params["week_from"], params["week_to"]) == ("2026-02-02", "2026-02-08")


async def test_acknowledge_mid_week_posts_monday(parent, server):
    await parent.acknowledge_journal(9002, date(2026, 2, 4))

    (post,) = _sent(server, "POST")
    body = json.loads(post.content)
    assert body["week"] == "2026-02-02"
    assert (body["parent_profile_id"], body["student_profile_id"]) == (7001, 9002)
    assert re.fullmatch(r"\d\d\.\d\d\.\d{4} \d\d:\d\d", body["created_at"])


async def test_acknowledge_already_acknowledged_week_does_not_post(parent, server):
    server.fake.add(f"GET {ACKS}", [ACK])

    await parent.acknowledge_journal(9001)

    assert _sent(server, "POST") == []


async def test_acknowledge_network_failure_is_write_uncertain(parent, server):
    server.fake.fail(f"POST {ACKS}", httpx.ConnectError("обрыв"))

    with pytest.raises(errors.WriteUncertain):
        await parent.acknowledge_journal(9001)


@pytest.mark.parametrize("call", ["journal_acks", "acknowledge_journal"])
async def test_unknown_child_is_not_found_before_journal_request(parent, server, call):
    with pytest.raises(errors.NotFound):
        await getattr(parent, call)(999)

    assert _sent(server, "GET") == [] and _sent(server, "POST") == []


async def test_period_longer_than_31_days_is_bad_request(parent):
    with pytest.raises(errors.BadRequest):
        await parent.journal_acks(9001, date(2026, 1, 1), date(2026, 3, 1))


async def test_acknowledge_future_week_is_bad_request_before_request(parent, server):
    # «Сегодня» — среда 4 февраля 2026: следующая неделя ещё не наступила.
    with pytest.raises(errors.BadRequest):
        await parent.acknowledge_journal(9001, date(2026, 2, 9))

    assert _sent(server, "GET") == [] and _sent(server, "POST") == []


async def test_acknowledge_current_week_on_sunday_is_allowed(parent, server):
    await parent.acknowledge_journal(9001, date(2026, 2, 8))

    assert len(_sent(server, "POST")) == 1
