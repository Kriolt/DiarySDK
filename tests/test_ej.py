"""Чтения журнала ej/core/family: учителя школы и академические задолженности."""

import dataclasses

import pytest

from diarysdk._gateway import DiaryGateway
from diarysdk._mapping import ej as ej_mapping
from diarysdk._port import Ctx
from tests.fakes import HOSTS, STUDENT, FakeTransport

TEACHERS = "/api/ej/core/family/v1/teacher_profiles"
DEBTS = "/api/ej/core/family/v1/academic_debts"
PARENT = dataclasses.replace(STUDENT, access="parent", parent_profile_id=STUDENT.profile_id)


def teacher(i: int) -> dict:
    return {
        "id": i,
        "user_id": 500 + i,
        "gusoev_login": None,
        "name": f"Учитель {i}",
        "school_id": STUDENT.school_id,
        "type": "teacher",
        "roles": ["teacher"],
        "subjects": [{"id": 10, "name": "Алгебра", "is_curriculum_subject": True}],
    }


DEBT = {
    "student_profile_id": STUDENT.student_id,
    "subject_id": 10,
    "subject_name": "Алгебра",
    "original_final_mark": None,
    "academic_debt_attempts": [{"academic_debt_final_mark": {"value": "4"}}],
}


class PagedFake(FakeTransport):
    """Учителя по страницам: ответ на страницу N — pages[N], дальше — последняя."""

    def __init__(self, pages):
        super().__init__()
        self.pages = pages

    async def send(self, method, url, **kwargs):
        page = int((kwargs.get("params") or {}).get("page", 1))
        self.add(TEACHERS, self.pages[min(page, len(self.pages)) - 1])
        return await super().send(method, url, **kwargs)


@pytest.fixture
def fake():
    return FakeTransport()


@pytest.fixture
def gateway(fake):
    return DiaryGateway(fake, HOSTS)


def test_teacher_keeps_public_fields_only():
    (result,) = ej_mapping.teachers([teacher(1)])

    assert (result.id, result.name, result.roles) == (1, "Учитель 1", ["teacher"])
    assert [(s.id, s.name) for s in result.subjects] == [(10, "Алгебра")]
    assert "user_id" not in result.model_dump()


def test_debts_are_only_the_childs_own():
    rows = [DEBT, {**DEBT, "student_profile_id": 9999}, {**DEBT, "student_profile_id": None}]

    (debt,) = ej_mapping.academic_debts(rows, STUDENT.student_id)

    assert (debt.subject.id, debt.subject.name) == (10, "Алгебра")
    assert debt.attested is True


def test_debt_without_marks_is_not_attested():
    row = {**DEBT, "academic_debt_attempts": [{"academic_debt_final_mark": None}]}

    (debt,) = ej_mapping.academic_debts([row], STUDENT.student_id)

    assert debt.attested is False


async def test_school_teachers_read_every_page():
    fake = PagedFake([[teacher(i) for i in range(50)], [teacher(50), teacher(51)]])
    gateway = DiaryGateway(fake, HOSTS)

    result = await gateway.school_teachers(Ctx(token="t.t.t", student=STUDENT), "Ив")

    assert len(result) == 52
    first = fake.sent[0]
    assert first.params == {
        "school_id": str(STUDENT.school_id),
        "with_virtual_teachers": "false",
        "full_list_teachers": "true",
        "per_page": "50",
        "page": "1",
        "user_sub_name": "Ив",
    }
    assert [r.params["page"] for r in fake.sent] == ["1", "2"]


async def test_school_teachers_stop_when_page_repeats():
    # Дневник проигнорировал page и отдаёт одну и ту же страницу.
    fake = PagedFake([[teacher(i) for i in range(50)]])
    gateway = DiaryGateway(fake, HOSTS)

    result = await gateway.school_teachers(Ctx(token="t.t.t", student=STUDENT), None)

    assert len(fake.sent) == 2
    assert len(result) == 50


async def test_school_teachers_stop_at_page_limit():
    class Endless(PagedFake):
        async def send(self, method, url, **kwargs):
            page = int(kwargs["params"]["page"])
            self.add(TEACHERS, [teacher(page * 100 + i) for i in range(50)])
            return await FakeTransport.send(self, method, url, **kwargs)

    fake = Endless([])
    await DiaryGateway(fake, HOSTS).school_teachers(Ctx(token="t.t.t", student=STUDENT), None)

    assert len(fake.sent) == 20


@pytest.mark.parametrize(
    ("ctx_student", "profile_type"), [(STUDENT, "student"), (PARENT, "parent")]
)
async def test_academic_debts_request(gateway, fake, ctx_student, profile_type):
    fake.add(DEBTS, [DEBT])

    result = await gateway.academic_debts(Ctx(token="t.t.t", student=ctx_student), 2025)

    assert len(result) == 1
    sent = fake.sent[0]
    assert sent.params == {"class_unit_ids": str(STUDENT.class_unit_id), "academic_year_id": "13"}
    assert sent.header("profile-type") == profile_type
