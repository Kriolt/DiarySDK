import pytest

from diarysdk._mapping.subjects import subjects
from diarysdk._wire.mobile import SubjectsMarks
from tests.fakes import fixture

ALGEBRA_MARK = {
    "id": 10001,
    "date": "2026-10-20",
    "subject": {"id": 101, "name": "Алгебра"},
    "value": "9",
    "scale": "ten",
    "five": 4.5,
    "hundred": 90.0,
    "weight": 2,
    "control_form": "Контрольная работа",
    "comment": None,
    "is_exam": False,
    "is_point": False,
    "point_date": None,
    "created_at": "2026-10-20T10:15:00+03:00",
    "ten": None,
    "nmax": 10.0,
    "has_files": None,
    "updated_at": None,
    "criteria": None,
}


def mapped(data=None):
    model = SubjectsMarks.model_validate(data or fixture("subject_marks.json"))
    return [s.model_dump(mode="json") for s in subjects(model)]


def test_subject_with_marks():
    algebra = mapped()[0]

    assert algebra == {
        "subject": {"id": 101, "name": "Алгебра"},
        # average_by_all — средний самого ученика; поле дневника average
        # (у всех 0.00 в октябре) не отдаём.
        "average": 4.5,
        "dynamic": "UP",
        "year_mark": None,
        "periods": [
            {
                "title": "1 четверть",
                "start": "2026-09-01",
                "end": "2026-10-26",
                "average": 4.5,
                "final_mark": None,
                "marks": [ALGEBRA_MARK],
                "marks_count": 1,
                "dynamic": "UP",
                # Цель периода: до «5» нужно ещё две оценки, путь — одна «5» веса 2.
                "target": {
                    "value": 5,
                    "round": "4.5",
                    "remain": 2,
                    "paths": [{"value": 5, "weight": 2, "remain": 1}],
                },
            }
        ],
    }


def test_subject_without_marks_has_null_average_not_zero():
    drawing = mapped()[1]

    assert drawing["subject"] == {"id": 109, "name": "Черчение"}
    assert drawing["average"] is None
    assert drawing["periods"][0]["average"] is None
    assert drawing["periods"][0]["target"] is None
    assert drawing["periods"][0]["marks"] == []


def test_final_mark_and_year_mark_are_text():
    data = fixture("subject_marks.json")
    data["payload"][0]["year_mark"] = 5
    data["payload"][0]["periods"][0]["fixed_value"] = "9"

    algebra = mapped(data)[0]

    assert algebra["year_mark"] == "5"
    assert algebra["periods"][0]["final_mark"] == "9"


def test_empty_payload_is_empty_list():
    assert mapped({"payload": None}) == []


def detail(data=None):
    from diarysdk._mapping.subjects import subject_detail
    from diarysdk._wire.mobile import SubjectMarksForSubject

    model = SubjectMarksForSubject.model_validate(data or fixture("subject_marks_for_subject.json"))
    return subject_detail(model).model_dump(mode="json")


def test_subject_detail_with_periods_target_and_marks():
    result = detail()

    assert result["subject_id"] == 101
    assert result["subject_name"] == "Алгебра"
    assert result["average_five"] == 4.5
    assert result["average_by_all"] == 4.5
    assert result["dynamic"] == "UP"
    [period] = result["periods"]
    assert period["title"] == "1 четверть"
    assert period["start"] == "2026-09-01"
    assert period["end"] == "2026-10-26"
    assert period["value"] == "4.50"
    assert period["fixed_value"] is None
    assert period["count"] == 1
    assert period["target"] == {
        "value": 5,
        "round": "4.5",
        "remain": 2,
        "paths": [{"value": 5, "weight": 2, "remain": 1}],
    }
    # Десятибалльная «9» разбирается так же, как в /v1/marks: five=4.5.
    assert period["marks"] == [{**ALGEBRA_MARK, "ten": None}]
    assert period["marks"][0]["five"] == 4.5


def test_subject_detail_average_five_is_the_diary_average_parsed():
    data = fixture("subject_marks_for_subject.json")
    data["average"] = "3.75"

    assert detail(data)["average_five"] == 3.75


@pytest.mark.parametrize("raw", ["0.00", "нет", None, ""])
def test_subject_detail_average_without_value_is_null(raw):
    data = fixture("subject_marks_for_subject.json")
    data["average"] = raw

    assert detail(data)["average_five"] is None
