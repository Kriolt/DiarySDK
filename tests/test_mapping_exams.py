import pytest

from diarysdk._mapping.exams import exams
from diarysdk.errors import UpstreamFormat
from tests.fakes import fixture

EXPECTED = [
    {"kind": "ОГЭ", "subject": "Математика", "date": "2026-05-20", "score": 25, "mark": "5"},
    {
        "kind": "Пробный ОГЭ",
        "subject": "Русский язык",
        "date": "2026-03-01",
        "score": 30,
        "mark": "4",
    },
]


def test_exams_from_fixture():
    assert [e.model_dump(mode="json") for e in exams(fixture("govexams.json"))] == EXPECTED


@pytest.mark.parametrize("wrapper", ["data", "payload"])
def test_list_wrapped_in_object_is_accepted(wrapper):
    assert len(exams({wrapper: fixture("govexams.json")})) == 2


def test_camel_case_keys_are_understood():
    [exam] = exams(
        [
            {
                "examType": "ЕГЭ",
                "subjectName": "Физика",
                "examDate": "2027-06-01",
                "testScore": 81.5,
                "mark": 5,
            }
        ]
    )

    assert exam.model_dump(mode="json") == {
        "kind": "ЕГЭ",
        "subject": "Физика",
        "date": "2027-06-01",
        "score": 81.5,
        "mark": "5",
    }


def test_no_exams_is_empty_list():
    assert exams([]) == []
    assert exams({"data": None}) == []


@pytest.mark.parametrize("data", ["ГИА", {"data": "много"}, 42])
def test_wrong_shape_is_format_error(data):
    with pytest.raises(UpstreamFormat):
        exams(data)
