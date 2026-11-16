"""Слой запросов gateway: тот же URL, параметры и заголовки, что увидит дневник.

Им пользуются и методы контракта, и тесты — поэтому фикстуры записывают ровно
те запросы, что делает сервис.
"""

from datetime import date

import pytest

from diarysdk._gateway import DiaryGateway
from diarysdk._transport import RatingOff
from tests.fakes import (
    AVATARS,
    CTX,
    DIARY_TOKEN,
    GUID,
    HOSTS,
    FakeTransport,
    fixture,
)


@pytest.fixture
def fake():
    return FakeTransport()


@pytest.fixture
def gateway(fake):
    return DiaryGateway(fake, HOSTS)


async def test_fetch_profile(gateway, fake):
    fake.add("/api/family/web/v1/profile", fixture("profile.json"))

    profile = await gateway.fetch_profile(DIARY_TOKEN)

    [sent] = fake.sent
    assert sent.url == "https://dnevnik.test/api/family/web/v1/profile"
    assert sent.call == "profile"
    assert profile.children[0].contingent_guid == GUID


async def test_fetch_school(gateway, fake):
    fake.add("/family/mobile/v1/school_info", fixture("school_info.json"))

    school = await gateway.fetch_school(CTX)

    [sent] = fake.sent
    assert sent.url == "https://school-api.test/family/mobile/v1/school_info"
    assert sent.params == {"school_id": "3001", "class_unit_id": "4001"}
    assert sent.header("profile-id") == "7001"
    assert sent.call == "school.info"
    assert school.name == "МБОУ «Гимназия № 0»"


async def test_fetch_marks(gateway, fake):
    fake.add("/family/mobile/v1/marks", fixture("marks.json"))

    marks = await gateway.fetch_marks(CTX, date(2026, 9, 1), date(2026, 10, 24))

    [sent] = fake.sent
    assert sent.params == {"student_id": "9001", "from": "2026-09-01", "to": "2026-10-24"}
    assert sent.header("profile-id") == "7001"
    assert sent.call == "marks"
    assert len(marks.payload) == 2


async def test_fetch_subjects(gateway, fake):
    fake.add("/family/mobile/v1/subject_marks", fixture("subject_marks.json"))

    subjects = await gateway.fetch_subjects(CTX)

    [sent] = fake.sent
    assert sent.params == {"student_id": "9001"}
    assert sent.call == "subjects.marks"
    assert subjects.payload[0].average_by_all == "4.50"


async def test_fetch_rating_class(gateway, fake):
    fake.add("/api/ej/rating/v1/rank/class", fixture("rating_class.json"))

    ranks = await gateway.fetch_rating_class(CTX, date(2026, 10, 24))

    [sent] = fake.sent
    assert sent.url == "https://dnevnik.test/api/ej/rating/v1/rank/class"
    assert sent.params == {"person_id": GUID, "classUnitId": "4001", "date": "2026-10-24"}
    assert sent.header("profile-id") == "7001"
    assert sent.header("x-mes-subsystem") == "familymp"
    assert sent.call == "rating.class"
    assert len(ranks) == 4


async def test_disabled_rating_is_recognized(gateway, fake):
    fake.add("/api/ej/rating/v1/rank/class", fixture("rating_disabled.json"))

    with pytest.raises(RatingOff):
        await gateway.fetch_rating_class(CTX, date(2026, 10, 24))


async def test_fetch_rating_subjects(gateway, fake):
    fake.add("/api/ej/rating/v1/rank/subjects", fixture("rating_subjects.json"))

    await gateway.fetch_rating_subjects(CTX, date(2026, 10, 24))

    [sent] = fake.sent
    assert sent.params == {"personId": GUID, "date": "2026-10-24"}
    assert sent.call == "rating.subjects"


async def test_fetch_rating_short(gateway, fake):
    fake.add("/api/ej/rating/v1/rank/rankShort", fixture("rating_short.json"))

    await gateway.fetch_rating_short(CTX, date(2026, 9, 1), date(2026, 10, 24))

    [sent] = fake.sent
    assert sent.params == {"personId": GUID, "beginDate": "2026-09-01", "endDate": "2026-10-24"}
    assert sent.call == "rating.short"


async def test_fetch_events_with_full_expand(gateway, fake):
    fake.add("/api/eventcalendar/v1/api/events", fixture("events.json"))

    await gateway.fetch_events(CTX, date(2026, 10, 19), date(2026, 10, 25))

    [sent] = fake.sent
    assert sent.url == "https://dnevnik.test/api/eventcalendar/v1/api/events"
    assert sent.params == {
        "person_ids": GUID,
        "begin_date": "2026-10-19",
        "end_date": "2026-10-25",
        "expand": "marks,homework,absence_reason_id,health_status,nonattendance_reason_id",
    }
    assert sent.header("x-mes-role") == "student"
    assert sent.header("x-mes-subsystem") == "familyweb"
    assert sent.call == "schedule.events"


async def test_fetch_events_with_given_expand(gateway, fake):
    fake.add("/api/eventcalendar/v1/api/events", fixture("events.json"))

    await gateway.fetch_events(
        CTX, date(2026, 10, 19), date(2026, 10, 25), expand="marks,health_status"
    )

    [sent] = fake.sent
    assert sent.params["expand"] == "marks,health_status"


async def test_fetch_lesson_goes_raw(gateway, fake):
    fake.add("/family/mobile/v1/lesson_schedule_items/20001", fixture("lesson.json"))

    lesson = await gateway.fetch_lesson(CTX, 20001)

    [sent] = fake.sent
    assert sent.params == {"student_id": "9001", "type": "PLAN"}
    assert sent.header("profile-id") == "7001"
    assert sent.call == "lesson"
    assert lesson["id"] == 20001


async def test_fetch_homework(gateway, fake):
    fake.add("/family/mobile/v1/homeworks", fixture("homeworks.json"))

    data = await gateway.fetch_homework(CTX, date(2026, 10, 24), date(2026, 10, 31))

    assert fake.sent[0].url == "https://school-api.test/family/mobile/v1/homeworks"
    assert data["payload"][0]["homework_entry_student_id"] == 40001


async def test_fetch_exams(gateway, fake):
    fake.add(f"/portfolio/app/persons/{GUID}/govexams/list/", fixture("govexams.json"))

    data = await gateway.fetch_exams(CTX)

    assert fake.sent[0].call == "exams"
    assert data[0]["exam_type"] == "ОГЭ"


async def test_fetch_final_marks_like_the_site(gateway, fake):
    fake.add("/api/family/web/v1/final_marks/v2", fixture("final_marks.json"))

    data = await gateway.fetch_final_marks(CTX, 2024)

    [sent] = fake.sent
    assert sent.url == "https://dnevnik.test/api/family/web/v1/final_marks/v2"
    # ID учебного года журнала: 2024/25 — 12 (по наблюдениям).
    assert sent.params == {
        "person_id": GUID,
        "academic_year_id": "12",
        "student_id": "9001",
        "is_year_marks_only": "true",
    }
    assert sent.header("profile-id") == "7001"
    assert sent.header("profile-type") == "student"
    assert sent.header("x-mes-roleid") == "1"
    assert sent.header("x-mes-subsystem") == "familyweb"
    assert sent.call == "final_marks"
    assert data["subjects"][0]["year_mark"] == "9"


async def test_fetch_person_data(gateway, fake):
    fake.add(f"/api/persondata/v1/persons/{GUID}", fixture("person_data.json"))

    card = await gateway.fetch_person_data(CTX)

    [sent] = fake.sent
    assert sent.url == f"https://dnevnik.test/api/persondata/v1/persons/{GUID}"
    assert sent.call == "persondata"
    assert card.snils == "555-666-777 88"


async def test_fetch_avatar_like_the_site(gateway, fake):
    fake.add(f"/api/avatarmanagement/v1/{GUID}", AVATARS)
    fake.add(f"/avatars/{GUID}", b"\x89PNG", content_type="image/png")

    response = await gateway.fetch_avatar(CTX)

    listing, image = fake.sent
    assert listing.url == f"https://dnevnik.test/api/avatarmanagement/v1/{GUID}"
    assert listing.header("x-mes-subsystem") == "headerweb"
    assert listing.header("x-mes-hostid") == "2"
    assert listing.call == "avatar.list"
    # Без image_id дневник отвечает 406 (по наблюдениям).
    assert image.url == f"https://dnevnik.test/avatars/{GUID}"
    assert image.params == {"image_id": "8801"}
    assert image.call == "avatar"
    assert response.content_type == "image/png"
