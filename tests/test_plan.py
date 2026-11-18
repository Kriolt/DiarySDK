"""Учебный план: рабочая программа группы, темы предмета, контрольные."""

import dataclasses
from datetime import date

import pytest

from diarysdk._gateway import DiaryGateway
from diarysdk._mapping import plan as plan_mapping
from diarysdk._port import Ctx
from tests.fakes import GUID, HOSTS, STUDENT, FakeTransport, fixture

PARENT = dataclasses.replace(STUDENT, access="parent", parent_profile_id=STUDENT.profile_id)


@pytest.fixture
def fake():
    fake = FakeTransport()
    fake.add("/api/family/web/v1/programs/lesson_plan", fixture("programs.json"))
    fake.add("/api/ej/plan/family/v1/thematic_frames", fixture("thematic_frames.json"))
    fake.add("/api/ej/plan/family/v1/test_lessons/period", fixture("test_lessons.json"))
    return fake


@pytest.fixture
def gateway(fake):
    return DiaryGateway(fake, HOSTS)


def test_work_program_keeps_modules_topics_lessons():
    (module,) = plan_mapping.work_program(fixture("programs.json"))

    assert (module.title, module.subject_id) == ("Модуль 1. Числа", 101)
    (topic,) = module.topics
    first, second = topic.lessons
    assert (first.lesson_id, first.date, first.ege_tasks) == (
        20001,
        date(2026, 9, 2),
        ["Задание 1"],
    )
    assert (second.lesson_id, second.date) == (None, None)


def test_subject_topics_keep_results_for_family():
    (topic,) = plan_mapping.subject_topics(fixture("thematic_frames.json"))

    assert (topic.id, topic.title) == (61, "Уравнения")
    (result,) = topic.results
    assert result.text == "Умеет решать уравнения"
    assert (result.type, result.mandatory) == ("предметный", "обязательный")


def test_control_works_mapping_and_null_items():
    (work,) = plan_mapping.control_works(fixture("test_lessons.json"))

    assert (work.date, work.subject.name, work.mark, work.lesson_id) == (
        date(2026, 10, 20),
        "Алгебра",
        "5",
        20001,
    )
    assert plan_mapping.control_works({"error": None, "items": None}) == []


@pytest.mark.parametrize(
    ("ctx_student", "profile_type"), [(STUDENT, "student"), (PARENT, "parent")]
)
async def test_plan_requests(gateway, fake, ctx_student, profile_type):
    ctx = Ctx(token="t.t.t", student=ctx_student)

    await gateway.work_program(ctx, 5001)
    await gateway.subject_topics(ctx, 101)
    await gateway.control_works(ctx, date(2026, 9, 1), date(2026, 12, 31))

    program, topics, works = fake.sent
    assert program.params == {
        "student_id": str(STUDENT.student_id),
        "group_id": "5001",
        "school_id": str(STUDENT.school_id),
    }
    assert topics.params == {"subject_id": "101", "student_profile_id": str(STUDENT.student_id)}
    assert works.params == {
        "student_profile_id": str(STUDENT.student_id),
        "from": "2026-09-01",
        "to": "2026-12-31",
        "student_person_id": GUID,
    }
    assert {r.header("profile-type") for r in fake.sent} == {profile_type}
