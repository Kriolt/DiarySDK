"""Методы контракта DiaryGateway: запрос через слой fetch_* и маппинг."""

import dataclasses
from datetime import date

import pytest

from diarysdk._gateway import DiaryGateway
from diarysdk._port import Ctx
from diarysdk.errors import (
    NetworkError,
    NoAvatar,
    NotForRole,
    NotFound,
    TokenInvalid,
    UpstreamError,
    UpstreamFormat,
    UpstreamTimeout,
)
from tests.fakes import AVATARS, CTX, GUID, HOSTS, STUDENT, FakeTransport, fixture
from tests.tokens import make_token, valid_token


@pytest.fixture
def fake():
    return FakeTransport()


@pytest.fixture
def gateway(fake):
    return DiaryGateway(fake, HOSTS)


async def test_student_context_from_profile_and_token_expiry(gateway, fake):
    fake.add("/api/family/web/v1/profile", fixture("profile.json"))
    token = make_token(STUDENT.expires_at)

    assert await gateway.student_context(token) == STUDENT


async def test_me_reads_profile_and_maps_it(fake):
    gateway = DiaryGateway(fake, HOSTS, today=lambda: date(2026, 10, 24))
    fake.add("/api/family/web/v1/profile", fixture("profile.json"))

    result = await gateway.me(Ctx(token="t.t.t", student=STUDENT))

    assert fake.sent[0].call == "profile"
    assert result.person.age == 16
    assert result.token.expires_at == STUDENT.expires_at


async def test_profile_without_children_is_format_error(gateway, fake):
    data = fixture("profile.json")
    data["children"] = []
    fake.add("/api/family/web/v1/profile", data)

    with pytest.raises(UpstreamFormat):
        await gateway.student_context(make_token(STUDENT.expires_at))


async def test_subjects_reads_subject_marks(gateway, fake):
    fake.add("/family/mobile/v1/subject_marks", fixture("subject_marks.json"))

    result = await gateway.subjects(Ctx(token="t.t.t", student=STUDENT))

    assert fake.sent[0].call == "subjects.marks"
    assert [s.subject.name for s in result] == ["Алгебра", "Черчение"]


async def test_rating_maps_class_rank(gateway, fake):
    fake.add("/api/ej/rating/v1/rank/class", fixture("rating_class.json"))

    result = await gateway.rating(Ctx(token="t.t.t", student=STUDENT), date(2026, 10, 24))

    assert result.me.place == 2
    assert fake.sent[0].params["date"] == "2026-10-24"


async def test_disabled_rating_is_enabled_false(gateway, fake):
    fake.add("/api/ej/rating/v1/rank/class", fixture("rating_disabled.json"))

    result = await gateway.rating(Ctx(token="t.t.t", student=STUDENT), date(2026, 10, 24))

    assert result.enabled is False


async def test_disabled_rating_gives_empty_subjects_and_history(gateway, fake):
    ctx = Ctx(token="t.t.t", student=STUDENT)
    fake.add("/api/ej/rating/v1/rank/subjects", fixture("rating_disabled.json"))
    fake.add("/api/ej/rating/v1/rank/rankShort", fixture("rating_disabled.json"))

    assert await gateway.rating_subjects(ctx, date(2026, 10, 24)) == []
    assert await gateway.rating_history(ctx, date(2026, 9, 1), date(2026, 10, 24)) == []


async def test_school_reads_school_info(gateway, fake):
    fake.add("/family/mobile/v1/school_info", fixture("school_info.json"))

    result = await gateway.school(Ctx(token="t.t.t", student=STUDENT))

    assert fake.sent[0].call == "school.info"
    assert result.website == "https://school.example.invalid"


async def test_marks_reads_marks_for_period(gateway, fake):
    fake.add("/family/mobile/v1/marks", fixture("marks.json"))

    result = await gateway.marks(
        Ctx(token="t.t.t", student=STUDENT), date(2026, 9, 1), date(2026, 10, 24)
    )

    assert fake.sent[0].params["from"] == "2026-09-01"
    assert [m.value for m in result] == ["9", "зч"]


async def test_schedule_reads_events_with_full_expand(gateway, fake):
    fake.add("/api/eventcalendar/v1/api/events", fixture("events.json"))

    result = await gateway.schedule(
        Ctx(token="t.t.t", student=STUDENT), date(2026, 10, 19), date(2026, 10, 25)
    )

    assert fake.sent[0].params["expand"] == (
        "marks,homework,absence_reason_id,health_status,nonattendance_reason_id"
    )
    assert [item.id for item in result] == [20001, 20002, 20003]
    assert result[0].health_status == "освобождён"


async def test_lesson_maps_raw_answer(gateway, fake):
    fake.add("/family/mobile/v1/lesson_schedule_items/20001", fixture("lesson.json"))

    result = await gateway.lesson(Ctx(token="t.t.t", student=STUDENT), 20001)

    assert result.topic == "Квадратные уравнения"


async def test_homework_maps_raw_answer(gateway, fake):
    fake.add("/family/mobile/v1/homeworks", fixture("homeworks.json"))

    result = await gateway.homework(
        Ctx(token="t.t.t", student=STUDENT), date(2026, 10, 24), date(2026, 10, 31)
    )

    assert fake.sent[0].params == {"from": "2026-10-24", "to": "2026-10-31", "student_id": "9001"}
    assert [h.id for h in result] == [40001, 40002]


async def test_exams_maps_raw_answer(gateway, fake):
    fake.add(f"/portfolio/app/persons/{GUID}/govexams/list/", fixture("govexams.json"))

    result = await gateway.exams(Ctx(token="t.t.t", student=STUDENT))

    assert fake.sent[0].header("cookie") == "aupd_current_role=4:1"
    assert [e.kind for e in result] == ["ОГЭ", "Пробный ОГЭ"]


async def test_final_marks_maps_raw_answer(gateway, fake):
    fake.add("/api/family/web/v1/final_marks/v2", fixture("final_marks.json"))

    result = await gateway.final_marks(Ctx(token="t.t.t", student=STUDENT), 2025)

    assert fake.sent[0].params["academic_year_id"] == "13"
    assert [(m.subject.name, m.year_mark) for m in result] == [
        ("Алгебра", "9"),
        ("Индивидуальный проект", "Зч"),
    ]


async def test_identity_asks_card_even_when_profile_has_snils(gateway, fake):
    # В карточке документы, место рождения и история обучения — она нужна
    # всегда, а не только ради СНИЛС.
    fake.add("/api/family/web/v1/profile", fixture("profile.json"))
    fake.add(f"/api/persondata/v1/persons/{GUID}", fixture("person_data.json"))

    result = await gateway.identity(Ctx(token="t.t.t", student=STUDENT))

    assert [s.call for s in fake.sent] == ["profile", "persondata"]
    assert result.person.snils == "111-222-333 44"


async def test_identity_without_card_is_still_an_answer(gateway, fake):
    fake.add("/api/family/web/v1/profile", fixture("profile.json"))
    fake.add(f"/api/persondata/v1/persons/{GUID}", {"message": "Forbidden"}, status=403)

    result = await gateway.identity(Ctx(token="t.t.t", student=STUDENT))

    assert result.person.snils == "111-222-333 44"
    # Поля карточки — пустые, а не ошибка всего ответа.
    assert result.person.birthplace is None
    assert result.person.documents == []
    assert result.person.education == []
    assert result.person.contacts == []


@pytest.mark.parametrize(
    ("status", "body"), [(404, {"message": "нет"}), (403, {"message": "Forbidden"})]
)
async def test_identity_without_card_access_or_card_is_still_an_answer(gateway, fake, status, body):
    fake.add("/api/family/web/v1/profile", fixture("profile.json"))
    fake.add(f"/api/persondata/v1/persons/{GUID}", body, status=status)

    result = await gateway.identity(Ctx(token="t.t.t", student=STUDENT))

    assert result.person.documents == []


@pytest.mark.parametrize(
    "failure",
    [
        UpstreamTimeout(),
        NetworkError(),
        UpstreamError(upstream_status=500),
        UpstreamError(upstream_status=502),
        UpstreamFormat(problems=["x: y"]),
        TokenInvalid(status=401),
    ],
    ids=lambda e: type(e).__name__ + str(getattr(e, "upstream_status", "") or ""),
)
async def test_identity_outage_of_card_is_not_an_empty_card(gateway, fake, failure):
    fake.add("/api/family/web/v1/profile", fixture("profile.json"))
    fake.fail(f"/api/persondata/v1/persons/{GUID}", failure)

    with pytest.raises(type(failure)):
        await gateway.identity(Ctx(token="t.t.t", student=STUDENT))


async def test_identity_card_server_error_status_is_an_error(gateway, fake):
    fake.add("/api/family/web/v1/profile", fixture("profile.json"))
    fake.add(f"/api/persondata/v1/persons/{GUID}", {"message": "сбой"}, status=503)

    with pytest.raises(UpstreamError) as info:
        await gateway.identity(Ctx(token="t.t.t", student=STUDENT))

    assert info.value.upstream_status == 503


async def test_identity_takes_snils_from_card_when_profile_is_empty(gateway, fake):
    data = fixture("profile.json")
    data["children"][0]["snils"] = None
    fake.add("/api/family/web/v1/profile", data)
    fake.add(f"/api/persondata/v1/persons/{GUID}", fixture("person_data.json"))

    result = await gateway.identity(Ctx(token="t.t.t", student=STUDENT))

    assert [s.call for s in fake.sent] == ["profile", "persondata"]
    assert result.person.snils == "555-666-777 88"


async def test_identity_survives_forbidden_card(gateway, fake):
    data = fixture("profile.json")
    data["children"][0]["snils"] = None
    fake.add("/api/family/web/v1/profile", data)
    fake.add(f"/api/persondata/v1/persons/{GUID}", {"message": "Forbidden"}, status=403)

    result = await gateway.identity(Ctx(token="t.t.t", student=STUDENT))

    assert result.person.snils is None
    assert result.person.last_name == "Тестов"


async def test_avatar_is_image_from_diary(gateway, fake):
    fake.add(f"/api/avatarmanagement/v1/{GUID}", AVATARS)
    fake.add(f"/avatars/{GUID}", b"\x89PNG", content_type="image/png")

    avatar = await gateway.avatar(Ctx(token="t.t.t", student=STUDENT))

    assert (avatar.content, avatar.content_type) == (b"\x89PNG", "image/png")


async def test_avatar_is_the_default_one(gateway, fake):
    fake.add(
        f"/api/avatarmanagement/v1/{GUID}",
        [{"id": 1, "url": "-", "default": False}, {"id": 2, "url": "-", "default": True}],
    )
    fake.add(f"/avatars/{GUID}", b"\x89PNG", content_type="image/png")

    await gateway.avatar(Ctx(token="t.t.t", student=STUDENT))

    assert fake.sent[-1].params == {"image_id": "2"}


async def test_empty_avatar_list_is_no_avatar_without_image_request(gateway, fake):
    fake.add(f"/api/avatarmanagement/v1/{GUID}", [])

    with pytest.raises(NoAvatar):
        await gateway.avatar(Ctx(token="t.t.t", student=STUDENT))
    assert len(fake.sent) == 1


@pytest.mark.parametrize(
    ("path", "body", "status", "content_type"),
    [
        ("/api/avatarmanagement/v1/{guid}", b"{}", 404, "application/json"),
        ("/avatars/{guid}", b"", 200, "image/png"),
        ("/avatars/{guid}", b"{}", 404, "application/json"),
    ],
)
async def test_missing_avatar_is_no_avatar(gateway, fake, path, body, status, content_type):
    fake.add(f"/api/avatarmanagement/v1/{GUID}", AVATARS)
    fake.add(f"/avatars/{GUID}", b"\x89PNG", content_type="image/png")
    fake.add(path.format(guid=GUID), body, status=status, content_type=content_type)

    with pytest.raises(NoAvatar):
        await gateway.avatar(Ctx(token="t.t.t", student=STUDENT))


@pytest.mark.parametrize("listing", [{"error": "x"}, [{"url": "-"}], [{"id": "первая"}]])
async def test_strange_avatar_list_is_format_error(gateway, fake, listing):
    fake.add(f"/api/avatarmanagement/v1/{GUID}", listing)

    with pytest.raises(UpstreamFormat):
        await gateway.avatar(Ctx(token="t.t.t", student=STUDENT))


async def test_non_image_answer_is_format_error_not_passed_through(gateway, fake):
    fake.add(f"/api/avatarmanagement/v1/{GUID}", AVATARS)
    fake.add(f"/avatars/{GUID}", "<html>Войдите</html>", content_type="text/html")

    with pytest.raises(UpstreamFormat):
        await gateway.avatar(Ctx(token="t.t.t", student=STUDENT))


async def test_subject_rating_is_class_rank_for_one_subject(gateway, fake):
    fake.add("/api/ej/rating/v1/rank/class", fixture("rating_class.json"))

    result = await gateway.rating(Ctx(token="t.t.t", student=STUDENT), date(2026, 10, 24), 77)

    assert result.enabled is True
    assert result.me.place == 2
    assert result.total == len(fixture("rating_class.json"))
    assert fake.sent[0].params["subjectId"] == "77"


async def test_disabled_subject_rating_is_enabled_false(gateway, fake):
    fake.add("/api/ej/rating/v1/rank/class", fixture("rating_disabled.json"))

    result = await gateway.rating(Ctx(token="t.t.t", student=STUDENT), date(2026, 10, 24), 77)

    assert result.enabled is False


async def test_strange_subject_rating_is_format_error(gateway, fake):
    fake.add("/api/ej/rating/v1/rank/class", {"payload": "не список"})

    with pytest.raises(UpstreamFormat):
        await gateway.rating(Ctx(token="t.t.t", student=STUDENT), date(2026, 10, 24), 77)


@pytest.mark.parametrize("body", [b"", {"success": True}, {}])
async def test_homework_done_accepted_by_diary(gateway, fake, body):
    fake.add("/family/mobile/v1/homeworks/555/done", body)

    assert await gateway.set_homework_done(CTX, 555, True) is None
    assert fake.sent[0].method == "POST"


async def test_homework_undone_is_delete(gateway, fake):
    fake.add("/family/mobile/v1/homeworks/555/done", b"")

    await gateway.set_homework_done(CTX, 555, False)

    assert fake.sent[0].method == "DELETE"


async def test_homework_done_refused_by_diary_is_upstream_error(gateway, fake):
    fake.add("/family/mobile/v1/homeworks/555/done", {"success": False})

    with pytest.raises(UpstreamError) as caught:
        await gateway.set_homework_done(CTX, 555, True)
    assert caught.value.upstream_status == 200


async def test_homework_done_for_missing_homework_is_not_found(gateway, fake):
    fake.add("/family/mobile/v1/homeworks/555/done", {}, status=404)

    with pytest.raises(NotFound):
        await gateway.set_homework_done(CTX, 555, True)


async def test_password_login_goes_through_transport(gateway, fake):
    token = valid_token()
    fake.add("/lms/api/sessions", {"authentication_token": "code-1"})
    fake.add("/v3/auth/kauth/callback", b"", status=302, cookies={"aupd_token": token})

    assert await gateway.password_login("login", "secret") == token
    assert [(s.method, s.url, s.call) for s in fake.sent] == [
        ("POST", "https://dnevnik.test/lms/api/sessions", "login.password"),
        ("GET", "https://dnevnik.test/v3/auth/kauth/callback", "login.callback"),
    ]


async def test_notifications_reads_feed_and_maps_it(gateway, fake):
    fake.add("/family/mobile/v1/notifications/search", fixture("notifications.json"))

    result = await gateway.notifications(Ctx(token="t.t.t", student=STUDENT))

    assert fake.sent[0].call == "notifications"
    assert [n.event_type for n in result] == ["create_homework", "create_mark", "update_mark"]


async def test_periods_reads_schedules_and_maps_them(gateway, fake):
    fake.add("/family/mobile/v1/periods_schedules", fixture("periods_schedules.json"))

    result = await gateway.periods(
        Ctx(token="t.t.t", student=STUDENT), date(2026, 9, 1), date(2027, 8, 31)
    )

    assert fake.sent[0].call == "periods_schedules"
    assert fake.sent[0].params["from"] == "2026-09-01"
    assert [p.title for p in result] == ["Осенние каникулы", "День народного единства"]


async def test_curriculum_reads_plan_by_context_id(gateway, fake):
    fake.add("/family/mobile/v1/programs/parallel_curriculum/1", fixture("curriculum.json"))

    result = await gateway.curriculum(Ctx(token="t.t.t", student=STUDENT))

    assert fake.sent[0].call == "curriculum"
    assert result.title == "Учебный план 10 класса"


async def test_curriculum_without_id_is_not_found_and_asks_nothing(gateway, fake):
    ctx = Ctx(token="t.t.t", student=dataclasses.replace(STUDENT, parallel_curriculum_id=None))

    with pytest.raises(NotFound):
        await gateway.curriculum(ctx)

    assert fake.sent == []


async def test_subject_detail_asks_by_name_from_subject_list(gateway, fake):
    fake.add("/family/mobile/v1/subject_marks", fixture("subject_marks.json"))
    fake.add(
        "/family/mobile/v1/subject_marks/for_subject", fixture("subject_marks_for_subject.json")
    )

    result = await gateway.subject(Ctx(token="t.t.t", student=STUDENT), 101)

    assert [s.call for s in fake.sent] == ["subjects.marks", "subject_marks.for_subject"]
    assert fake.sent[1].params["subject_name"] == "Алгебра"
    assert fake.sent[1].params["student_id"] == str(STUDENT.student_id)
    assert result.average_five == 4.5


async def test_subject_detail_of_unknown_id_is_not_found_without_second_request(gateway, fake):
    fake.add("/family/mobile/v1/subject_marks", fixture("subject_marks.json"))

    with pytest.raises(NotFound):
        await gateway.subject(Ctx(token="t.t.t", student=STUDENT), 999)

    assert [s.call for s in fake.sent] == ["subjects.marks"]


async def test_mark_detail_reads_mark_of_own_student(gateway, fake):
    fake.add("/family/mobile/v1/marks/10001", fixture("mark_info.json"))

    result = await gateway.mark(Ctx(token="t.t.t", student=STUDENT), 10001)

    assert fake.sent[0].call == "mark.info"
    assert fake.sent[0].params == {"student_id": str(STUDENT.student_id)}
    assert result.value == "9"


async def test_unknown_mark_is_not_found(gateway, fake):
    fake.add("/family/mobile/v1/marks/999", b"", status=404)

    with pytest.raises(NotFound):
        await gateway.mark(Ctx(token="t.t.t", student=STUDENT), 999)


@pytest.mark.parametrize(("body", "status"), [(b"", 200), ("null", 200), ("{}", 200), (b"", 404)])
async def test_missing_settings_group_is_all_null(gateway, fake, body, status):
    fake.add("/api/usersettings/v1", body, status=status)

    result = await gateway.settings(Ctx(token="t.t.t", student=STUDENT))

    assert result.model_dump(mode="json") == {
        "goal": None,
        "theme": {"type": None, "is_automatic": None, "color_pattern": None},
        "schedule_type": None,
        "estimation_type": None,
    }


PARENT = dataclasses.replace(STUDENT, access="parent", parent_profile_id=STUDENT.profile_id)


async def test_final_marks_headers_follow_access(gateway, fake):
    fake.add("/api/family/web/v1/final_marks/v2", fixture("final_marks.json"))

    await gateway.final_marks(Ctx(token="t.t.t", student=STUDENT), 2025)
    await gateway.final_marks(Ctx(token="t.t.t", student=PARENT), 2025)

    student, parent = fake.sent
    assert (student.header("profile-type"), student.header("x-mes-roleid")) == ("student", "1")
    assert (parent.header("profile-type"), parent.header("x-mes-roleid")) == ("parent", None)


@pytest.mark.parametrize("method", ["exams", "avatar"])
async def test_parent_access_reads_without_parent_data_fail_before_request(gateway, fake, method):
    with pytest.raises(NotForRole) as error:
        await getattr(gateway, method)(Ctx(token="t.t.t", student=PARENT))

    assert error.value.role == "parent"
    assert fake.sent == []
