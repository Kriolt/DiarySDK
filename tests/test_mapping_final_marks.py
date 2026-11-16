import pytest

from diarysdk._mapping.final_marks import final_marks
from diarysdk.errors import UpstreamFormat
from tests.fakes import fixture


def test_final_marks_from_fixture():
    assert [m.model_dump(mode="json") for m in final_marks(fixture("final_marks.json"))] == [
        {
            "subject": {"id": 501, "name": "Алгебра"},
            "year_mark": "9",
            "attestation_mark": None,
            "training_camp_mark": None,
        },
        {
            "subject": {"id": 502, "name": "Индивидуальный проект"},
            "year_mark": "Зч",
            "attestation_mark": None,
            "training_camp_mark": None,
        },
    ]


def test_year_without_marks_is_empty_list():
    # Так дневник отвечает на текущий год, пока годовых нет, и на год до журнала.
    assert final_marks({"subjects": []}) == []


def test_numeric_marks_become_text():
    [mark] = final_marks(
        {"subjects": [{"id": 1, "name": "Химия", "year_mark": 8, "training_camp_mark": 5}]}
    )

    assert mark.year_mark == "8"
    assert mark.training_camp_mark == "5"


@pytest.mark.parametrize("data", [{}, [], {"subjects": "нет"}, {"subjects": [{"id": "x"}]}])
def test_changed_format_is_format_error(data):
    with pytest.raises(UpstreamFormat):
        final_marks(data)
