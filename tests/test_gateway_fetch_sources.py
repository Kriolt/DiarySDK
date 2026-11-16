"""Источники дневника, которые читает gateway.

Ожидаемые URL, параметры и заголовки — по протоколу дневника.
"""

from datetime import date

import pytest

from diarysdk._gateway import DiaryGateway
from tests.fakes import CTX, HOSTS, FakeTransport


@pytest.fixture
def fake():
    return FakeTransport()


@pytest.fixture
def gateway(fake):
    return DiaryGateway(fake, HOSTS)


SEP_1 = date(2026, 9, 1)
OCT_24 = date(2026, 10, 24)

MOBILE = [
    pytest.param(
        lambda gw: gw.fetch_notifications(CTX),
        "https://school-api.test/family/mobile/v1/notifications/search",
        {"student_id": "9001"},
        [],
        "notifications",
        id="notifications",
    ),
    pytest.param(
        lambda gw: gw.fetch_curriculum(CTX, 555),
        "https://school-api.test/family/mobile/v1/programs/parallel_curriculum/555",
        {"student_id": "9001"},
        {},
        "curriculum",
        id="curriculum",
    ),
    pytest.param(
        lambda gw: gw.fetch_periods_schedules(CTX, SEP_1, OCT_24),
        "https://school-api.test/family/mobile/v1/periods_schedules",
        {"student_id": "9001", "from": "2026-09-01", "to": "2026-10-24"},
        [],
        "periods_schedules",
        id="periods_schedules",
    ),
    pytest.param(
        lambda gw: gw.fetch_subject_marks_for_subject(CTX, "Алгебра"),
        "https://school-api.test/family/mobile/v1/subject_marks/for_subject",
        {"student_id": "9001", "subject_name": "Алгебра"},
        {},
        "subject_marks.for_subject",
        id="subject_marks_for_subject",
    ),
]


@pytest.mark.parametrize(("fetch", "url", "params", "body", "call"), MOBILE)
async def test_mobile_source_is_asked_for_this_student(
    gateway, fake, fetch, url, params, body, call
):
    fake.add(url.split(".test", 1)[1], body)

    await fetch(gateway)

    [sent] = fake.sent
    assert sent.method == "GET"
    assert sent.url == url
    assert sent.params == params
    assert sent.call == call


@pytest.mark.parametrize(
    "fetch",
    [lambda gw: gw.fetch_notifications(CTX)],
    ids=["notifications"],
)
async def test_family_mobile_sources_carry_profile_id(gateway, fake, fetch):
    fake.add("/family/mobile/v1/notifications/search", [])

    await fetch(gateway)

    [sent] = fake.sent
    assert sent.header("profile-id") == "7001"
    assert sent.header("x-mes-subsystem") == "familymp"
