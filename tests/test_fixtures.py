"""Синтетические фикстуры дневника проходят модели ответов (_wire).

Живого дневника в тестах нет, поэтому фикстуры написаны руками по формам
ответов. Этот тест держит их честными: фикстура, которую модель не приняла
бы, тестировала бы выдумку.
"""

import pytest

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
from tests.fakes import fixture, fixture_text, wire_list


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("profile.json", WebFamilyProfile),
        ("school_info.json", SchoolInfo),
        ("marks.json", Marks),
        ("subject_marks.json", SubjectsMarks),
        ("events.json", EventsResponse),
        ("person_data.json", PersonData),
        ("curriculum.json", ParallelCurriculum),
        ("subject_marks_for_subject.json", SubjectMarksForSubject),
        ("user_settings.json", UserSettings),
    ],
)
def test_object_fixture_passes_wire_model(name, model):
    model.model_validate_json(fixture_text(name))


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
def test_list_fixture_passes_wire_model(name, model, length):
    assert len(wire_list(model, fixture_text(name))) == length


def test_disabled_rating_is_not_a_rating_list():
    with pytest.raises(ValueError):
        wire_list(RatingRankClass, fixture_text("rating_disabled.json"))


@pytest.mark.parametrize("name", ["homeworks.json", "govexams.json", "lesson.json"])
def test_raw_fixture_is_json(name):
    assert fixture(name)
