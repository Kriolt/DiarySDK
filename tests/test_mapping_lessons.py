import pytest

from diarysdk._mapping.lessons import lesson
from diarysdk.errors import UpstreamFormat
from tests.fakes import fixture


def test_lesson_from_fixture():
    result = lesson(fixture("lesson.json")).model_dump(mode="json")

    assert result == {
        "id": 20001,
        "date": "2026-10-20",
        "start": "2026-10-20T08:30:00+03:00",
        "end": "2026-10-20T09:15:00+03:00",
        "subject": {"id": 101, "name": "Алгебра"},
        "room": "204",
        "topic": "Квадратные уравнения",
        "teacher": {
            "last_name": "Учителев",
            "first_name": "Иван",
            "middle_name": "Иванович",
            "sex": "male",
            "birth_date": "1980-01-01",
            "user_id": 5100,
        },
        "marks": [
            {
                "id": 10003,
                "date": "2026-10-20",
                "subject": {"id": 101, "name": "Алгебра"},
                "value": "8",
                "scale": "ten",
                "five": 4.0,
                "hundred": 80.0,
                "weight": 1,
                "control_form": "Работа на уроке",
                "comment": None,
                "is_exam": False,
                "is_point": False,
                "point_date": None,
                "created_at": "2026-10-20T09:00:00+03:00",
                "ten": None,
                "nmax": 10.0,
                "has_files": None,
                "updated_at": None,
                "criteria": [],
            }
        ],
        "homework": [
            {
                "text": "№ 1-5 стр. 10",
                # Вид и действие — с группы материалов.
                "materials": [
                    {
                        "title": "Задание.pdf",
                        "url": "https://dnevnik.test/files/zadanie.pdf",
                        "description": None,
                        "content_type": None,
                        "type_name": "Вложения",
                        "action_name": "Выполнить",
                    },
                    {
                        "title": "Видеоурок",
                        "url": "https://video.example.invalid/v1",
                        "description": None,
                        "content_type": None,
                        "type_name": "Вложения",
                        "action_name": "Выполнить",
                    },
                ],
            }
        ],
        "materials": [
            {
                "title": "Учебник, § 3",
                "url": "https://lib.example.invalid/p3",
                "description": None,
                "content_type": None,
                "type_name": None,
                "action_name": None,
            }
        ],
        "is_missed": False,
        "nonattendance_reason_id": None,
        "building": "Основное здание",
        "comment": None,
        "is_virtual": False,
        "lesson_type": "NORMAL",
        "lesson_education_type": "OO",
        "plan_id": 1,
        "group_id": 55,
        "theme": {
            "id": None,
            "title": None,
            "average_mark": None,
            "oge_task": None,
            "ege_task": None,
            "frames": [
                {
                    "id": 1,
                    "title": "Раздел",
                    "average_mark": None,
                    "oge_task": None,
                    "ege_task": ["1"],
                    "frames": [
                        {
                            "id": 2,
                            "title": "Тема",
                            "average_mark": None,
                            "oge_task": None,
                            "ege_task": None,
                            "frames": [
                                {
                                    "id": 3,
                                    "title": "Подтема",
                                    "average_mark": None,
                                    "oge_task": None,
                                    "ege_task": None,
                                    "frames": [],
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        # Как пришли: в наблюдениях всегда null или пустые.
        "disease_status": None,
        "is_remote": None,
        "control": None,
        "evaluation": None,
        "teacher_comments": [],
        "student_work": None,
        "theme_mastery": None,
        "kr_attachments": [],
        "content": [],
    }


def test_unknown_shape_fields_go_as_is():
    data = fixture("lesson.json")
    data["disease_status_type"] = "болезнь"
    data["teacher_comments"] = [{"text": "Молодец"}]

    result = lesson(data)

    assert result.disease_status == "болезнь"
    assert result.teacher_comments == [{"text": "Молодец"}]


def test_ten_point_mark_survives():
    data = fixture("lesson.json")
    data["marks"][0]["value"] = "9"
    data["marks"][0]["values"][0]["grade"] = {"origin": "9", "five": 4.5, "hundred": 90, "ten": 9}

    assert lesson(data).marks[0].five == 4.5
    assert lesson(data).marks[0].ten == 9.0


@pytest.mark.parametrize("data", [[], "урок", {"id": "не-число"}, {"marks": "много"}])
def test_wrong_shape_is_format_error(data):
    with pytest.raises(UpstreamFormat):
        lesson(data)


def test_minimal_lesson_is_mostly_null():
    result = lesson({"id": 1})

    assert result.id == 1
    assert result.start is None
    assert result.teacher is None
    assert result.marks == []
