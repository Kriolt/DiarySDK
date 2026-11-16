"""Модели _wire и запросы _api: фикстуры проходят модели, неверная форма даёт
UpstreamFormat без значений, незнакомые поля сохраняются."""

import json
from datetime import date
from urllib.parse import urlsplit

import pytest
from pydantic import TypeAdapter

from diarysdk._api.mobile import MobileAPI
from diarysdk._api.web import WebAPI
from diarysdk._mapping.common import field
from diarysdk._transport import DiaryResponse
from diarysdk._wire.common import parse, parse_list
from diarysdk._wire.mobile import (
    Marks,
    Notification,
    ParallelCurriculum,
    PeriodsSchedules,
    SchoolInfo,
    SubjectMarksForSubject,
    SubjectsMarks,
    UserSettings,
)
from diarysdk._wire.rating import RatingRankClass, RatingRankShort, RatingRankSubject
from diarysdk._wire.web import EventsResponse, PersonData, WebFamilyProfile
from diarysdk.errors import UpstreamFormat
from tests.fakes import HOSTS, FakeTransport, fixture, fixture_text

TOKEN = "header.payload.signature"
SEP_1, OCT_24 = date(2026, 9, 1), date(2026, 10, 24)


def response(text: str | bytes) -> DiaryResponse:
    body = text.encode() if isinstance(text, str) else text
    return DiaryResponse(status=200, content_type="application/json", body=body)


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("school_info.json", SchoolInfo),
        ("marks.json", Marks),
        ("subject_marks.json", SubjectsMarks),
        ("curriculum.json", ParallelCurriculum),
        ("subject_marks_for_subject.json", SubjectMarksForSubject),
        ("user_settings.json", UserSettings),
        ("profile.json", WebFamilyProfile),
        ("events.json", EventsResponse),
        ("person_data.json", PersonData),
    ],
)
def test_object_fixture_passes_its_model(name, model):
    assert parse(model, response(fixture_text(name)))


@pytest.mark.parametrize(
    ("name", "model", "length"),
    [
        ("notifications.json", Notification, 3),
        ("periods_schedules.json", PeriodsSchedules, 2),
        ("rating_class.json", RatingRankClass, 4),
        ("rating_subjects.json", RatingRankSubject, 2),
        ("rating_short.json", RatingRankShort, 2),
    ],
)
def test_list_fixture_passes_its_model(name, model, length):
    assert len(parse_list(model, response(fixture_text(name)))) == length


def test_disabled_rating_is_not_a_rating_list():
    with pytest.raises(UpstreamFormat):
        parse_list(RatingRankClass, response(fixture_text("rating_disabled.json")))


@pytest.mark.parametrize("body", ["null", "{}", "[1]"])
def test_null_list_is_format_error(body):
    with pytest.raises(UpstreamFormat) as info:
        parse_list(Notification, response(body))

    assert info.value.problems


def test_null_list_field_is_format_error_with_path_only():
    data = {"sections": [{"knowledge_field_name": "Язык", "subjects": None}]}

    with pytest.raises(UpstreamFormat) as info:
        parse(ParallelCurriculum, response(json.dumps(data, ensure_ascii=False)))

    assert info.value.problems == ["sections.0.subjects: list_type"]
    assert "Язык" not in str(info.value)


def test_wrong_type_hides_the_value():
    with pytest.raises(UpstreamFormat) as info:
        parse(SchoolInfo, response('{"id": "Иванов"}'))

    assert info.value.problems == ["id: int_parsing"]
    assert "Иванов" not in str(info.value)
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__


@pytest.mark.parametrize("body", ["", "<html>Технические работы</html>"])
def test_empty_or_html_body_is_format_error(body):
    with pytest.raises(UpstreamFormat):
        parse(Marks, response(body))


def test_unknown_fields_are_kept():
    item = fixture("rating_class.json")[0]
    item["rank"]["rankPlace30"] = 7
    item["unknown"] = {"x": 1}

    [parsed] = TypeAdapter(list[RatingRankClass]).validate_python([item])

    assert field(parsed.rank, "rankPlace30") == 7
    assert parsed.unknown == {"x": 1}


def test_missing_unknown_field_is_none():
    # У четвёртой записи фикстуры значений за 30 дней нет.
    [rank] = [
        item.rank
        for item in TypeAdapter(list[RatingRankClass]).validate_python(
            [fixture("rating_class.json")[3]]
        )
    ]

    assert field(rank, "rankPlace30") is None


MOBILE_HEADERS = {"x-mes-subsystem": "familymp", "client-type": "diary-mobile", "profile-id": "11"}
READS = [
    pytest.param(
        lambda api: api.get_marks(student_id=33, profile_id=11, from_date=SEP_1, to_date=OCT_24),
        "marks.json",
        "https://school-api.test/family/mobile/v1/marks",
        {"student_id": "33", "from": "2026-09-01", "to": "2026-10-24"},
        id="marks",
    ),
    pytest.param(
        lambda api: api.get_subjects_marks(profile_id=11, student_id=33),
        "subject_marks.json",
        "https://school-api.test/family/mobile/v1/subject_marks",
        {"student_id": "33"},
        id="subjects",
    ),
    pytest.param(
        lambda api: api.get_subject_marks_for_subject(
            student_id=33, profile_id=11, subject_name="Алгебра"
        ),
        "subject_marks_for_subject.json",
        "https://school-api.test/family/mobile/v1/subject_marks/for_subject",
        {"student_id": "33", "subject_name": "Алгебра"},
        id="for_subject",
    ),
    pytest.param(
        lambda api: api.get_school_info(profile_id=11, school_id=5, class_unit_id=22),
        "school_info.json",
        "https://school-api.test/family/mobile/v1/school_info",
        {"school_id": "5", "class_unit_id": "22"},
        id="school",
    ),
    pytest.param(
        lambda api: api.get_notifications(student_id=33, profile_id=11),
        "notifications.json",
        "https://school-api.test/family/mobile/v1/notifications/search",
        {"student_id": "33"},
        id="notifications",
    ),
    pytest.param(
        lambda api: api.get_periods_schedules(
            student_id=33, profile_id=11, from_date=SEP_1, to_date=OCT_24
        ),
        "periods_schedules.json",
        "https://school-api.test/family/mobile/v1/periods_schedules",
        {"student_id": "33", "from": "2026-09-01", "to": "2026-10-24"},
        id="periods",
    ),
    pytest.param(
        lambda api: api.get_programs_parallel_curriculum(
            curriculum_id=1, profile_id=11, student_id=33
        ),
        "curriculum.json",
        "https://school-api.test/family/mobile/v1/programs/parallel_curriculum/1",
        {"student_id": "33"},
        id="curriculum",
    ),
    pytest.param(
        lambda api: api.get_rating_rank_class(
            profile_id=11, person_id="guid-1", class_unit_id=22, on=OCT_24
        ),
        "rating_class.json",
        "https://dnevnik.test/api/ej/rating/v1/rank/class",
        {"person_id": "guid-1", "classUnitId": "22", "date": "2026-10-24"},
        id="rating_class",
    ),
    pytest.param(
        lambda api: api.get_rating_rank_subjects(profile_id=11, person_id="guid-1", on=OCT_24),
        "rating_subjects.json",
        "https://dnevnik.test/api/ej/rating/v1/rank/subjects",
        {"personId": "guid-1", "date": "2026-10-24"},
        id="rating_subjects",
    ),
    pytest.param(
        lambda api: api.get_rating_rank_short(
            profile_id=11, person_id="guid-1", begin_date=SEP_1, end_date=OCT_24
        ),
        "rating_short.json",
        "https://dnevnik.test/api/ej/rating/v1/rank/rankShort",
        {"personId": "guid-1", "beginDate": "2026-09-01", "endDate": "2026-10-24"},
        id="rating_short",
    ),
]


@pytest.mark.parametrize(("call", "name", "url", "params"), READS)
async def test_mobile_request_goes_where_the_diary_expects(call, name, url, params):
    fake = FakeTransport()
    fake.add(urlsplit(url).path, fixture(name))

    await call(MobileAPI(fake, HOSTS, TOKEN))

    [sent] = fake.sent
    assert (sent.method, sent.url, sent.params) == ("GET", url, params)
    for header, value in MOBILE_HEADERS.items():
        assert sent.header(header) == value
    assert sent.header("auth-token") == TOKEN
    assert sent.header("authorization") == f"Bearer {TOKEN}"


WEB = [
    pytest.param(
        lambda api: api.get_family_web_profile(),
        "profile.json",
        "https://dnevnik.test/api/family/web/v1/profile",
        {"nocache": "true"},
        {"x-mes-subsystem": "familyweb", "profile-id": None},
        id="profile",
    ),
    pytest.param(
        lambda api: api.get_person_data(person_id="guid-1"),
        "person_data.json",
        "https://dnevnik.test/api/persondata/v1/persons/guid-1",
        {},
        {"x-mes-subsystem": "headerweb"},
        id="person_data",
    ),
    pytest.param(
        lambda api: api.get_events(
            person_id="guid-1",
            mes_role="student",
            begin_date=date(2026, 10, 19),
            end_date=date(2026, 10, 25),
            expand="marks,homework",
        ),
        "events.json",
        "https://dnevnik.test/api/eventcalendar/v1/api/events",
        {
            "person_ids": "guid-1",
            "begin_date": "2026-10-19",
            "end_date": "2026-10-25",
            "expand": "marks,homework",
        },
        {"x-mes-subsystem": "familyweb", "x-mes-role": "student"},
        id="events",
    ),
]


@pytest.mark.parametrize(("call", "name", "url", "params", "headers"), WEB)
async def test_web_request_goes_where_the_diary_expects(call, name, url, params, headers):
    fake = FakeTransport()
    fake.add(urlsplit(url).path, fixture(name))

    await call(WebAPI(fake, HOSTS, TOKEN))

    [sent] = fake.sent
    assert (sent.method, sent.url, sent.params) == ("GET", url, params)
    for header, value in headers.items():
        assert sent.header(header) == value
    assert sent.header("auth-token") == TOKEN


async def test_wrong_shape_in_profile_is_format_error_without_values():
    fake = FakeTransport()
    fake.add("/api/family/web/v1/profile", {"profile": {"id": "Иванов"}})

    with pytest.raises(UpstreamFormat) as info:
        await WebAPI(fake, HOSTS, TOKEN).get_family_web_profile()

    assert info.value.problems == ["profile.id: int_parsing"]
    assert "Иванов" not in str(info.value)


async def test_null_item_in_children_is_format_error():
    data = {"children": [None]}

    with pytest.raises(UpstreamFormat) as info:
        parse(WebFamilyProfile, response(json.dumps(data)))

    assert info.value.problems == ["children.0: model_type"]


def test_web_models_keep_unknown_fields():
    data = fixture("profile.json")
    data["children"][0]["grade_book_number"] = "ЛД-0042"

    profile = WebFamilyProfile.model_validate(data)

    assert field(profile.children[0], "grade_book_number") == "ЛД-0042"


def test_rating_wire_missing_nullable_keys_default_to_none():
    from diarysdk._wire.rating import RatingRankClass

    item = RatingRankClass.model_validate({})

    assert item.person_id is None
    assert item.previous_rank is None
    assert item.image_id is None


def test_rating_wire_reads_camel_case_keys():
    from diarysdk._wire.rating import Rank

    assert Rank.model_validate({"rankPlace": 3, "averageMarkFive": 4.5}).rank_place == 3
