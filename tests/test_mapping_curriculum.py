from diarysdk._mapping.curriculum import curriculum
from diarysdk._wire.mobile import ParallelCurriculum
from tests.fakes import fixture


def mapped(data=None):
    return curriculum(
        ParallelCurriculum.model_validate(fixture("curriculum.json") if data is None else data)
    ).model_dump(mode="json")


def test_curriculum_with_literal_values():
    assert mapped() == {
        "title": "Учебный план 10 класса",
        "short_name": "УП-10",
        "education_level": "Среднее общее образование",
        "education_form": "Очная",
        "class_level_id": 10,
        "hours": 34,
        "days_in_week": 5,
        "is_adapted": False,
        "comments": None,
        "specialization": "Универсальный",
        "study_profile": None,
        "sections": [
            {
                "knowledge_field": "Математика и информатика",
                "subjects": [
                    {
                        "subject_id": 101,
                        "subject_name": "Алгебра",
                        "parent_subject_id": None,
                        "total_hours": 136,
                        "passed_hours": 40,
                        "min_hours_per_week": 3,
                        "max_hours_per_week": 4,
                        "teachers": ["Тестова Анна Ивановна"],
                        "weeks": [
                            {"week_number": 1, "hours": 4},
                            {"week_number": 2, "hours": 3},
                        ],
                    },
                    {
                        "subject_id": 102,
                        "subject_name": "Геометрия",
                        "parent_subject_id": 101,
                        "total_hours": 68,
                        "passed_hours": 20,
                        "min_hours_per_week": 2,
                        "max_hours_per_week": 2,
                        "teachers": [],
                        "weeks": [],
                    },
                ],
            }
        ],
        "weeks": [
            {
                "week_number": 1,
                "begin": "2026-09-01",
                "end": "2026-09-06",
                "hours": 34,
                "days": 5,
            }
        ],
    }


def test_internal_ids_are_not_taken():
    text = str(mapped())

    assert "555" not in text
    assert "777" not in text
    assert "integration" not in text


def test_empty_curriculum():
    result = mapped({})

    assert result["sections"] == []
    assert result["weeks"] == []
    assert result["title"] is None
