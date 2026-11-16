import json
from datetime import date

import pytest

from diarysdk._mapping.me import me, study_profile
from diarysdk._wire.web import WebFamilyProfile
from diarysdk.errors import UpstreamFormat
from tests.fakes import STUDENT, fixture

TODAY = date(2026, 10, 24)


def profile(**child_changes):
    data = fixture("profile.json")
    data["children"][0].update(child_changes)
    return WebFamilyProfile.model_validate(data)


def test_me_from_profile_fixture():
    result = me(profile(), STUDENT.expires_at, TODAY).model_dump(mode="json", by_alias=True)

    assert result == {
        "person": {
            "last_name": "Тестов",
            "first_name": "Тест",
            "middle_name": "Тестович",
            "sex": "male",
            "age": 16,
            "guid": "00000000-0000-4000-8000-000000000001",
        },
        "school": {
            "id": 3001,
            "name": "МБОУ «Гимназия № 0»",
            "short_name": "Гимназия № 0",
            "municipality": "г.о. Тестовый",
        },
        "class": {"id": 4001, "name": "10-Ф", "level": 10},
        "study_profile": "ф.-м.",
        "sections": [{"id": 8001, "name": "Робототехника"}],
        "enrolled_on": "2016-09-01",
        "token": {"expires_at": "2026-11-01T12:00:00Z"},
    }


def test_me_has_no_contacts_snils_or_representatives():
    text = json.dumps(me(profile(), STUDENT.expires_at, TODAY).model_dump(mode="json"))

    for forbidden in ["111-222-333 44", "+7 000 000-00-01", "student@", "Представителева"]:
        assert forbidden not in text


def test_age_counts_only_full_years():
    assert me(profile(), STUDENT.expires_at, date(2026, 3, 14)).person.age == 15
    assert me(profile(), STUDENT.expires_at, date(2026, 3, 15)).person.age == 16


def test_missing_fields_are_null():
    result = me(
        profile(birth_date=None, sections=None, enrollment_date=None, school=None),
        STUDENT.expires_at,
        TODAY,
    )

    assert result.person.age is None
    assert result.sections == []
    assert result.enrolled_on is None
    assert result.school.name is None


def test_sections_that_are_not_objects_are_skipped():
    result = me(
        profile(sections=["кружок", {"id": 1, "name": "Шахматы"}, {"x": 1}]),
        STUDENT.expires_at,
        TODAY,
    )

    assert [s.model_dump() for s in result.sections] == [
        {"id": 1, "name": "Шахматы"},
        {"id": None, "name": None},
    ]


def test_profile_without_child_is_format_error():
    data = fixture("profile.json")
    data["children"] = []

    with pytest.raises(UpstreamFormat):
        me(WebFamilyProfile.model_validate(data), STUDENT.expires_at, TODAY)


@pytest.mark.parametrize(
    ("groups", "expected"),
    [
        (["Алгебра 10-Ф ф.-м.", "Физика 10-Ф ф.-м.", "Английский 10-Ф гр. 1"], "ф.-м."),
        (["Химия 10-Б х.-б.", "Биология х.-б."], "х.-б."),
        (["Алгебра ф.-м.", "Химия х.-б."], None),
        (["Алгебра 10-А", "Английский гр. 2"], None),
        ([], None),
    ],
)
def test_study_profile_is_the_only_abbreviation_in_group_names(groups, expected):
    assert study_profile(groups) == expected
