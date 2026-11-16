from diarysdk._mapping.marks import marks
from diarysdk._wire.mobile import Marks
from tests.fakes import fixture


def test_marks_from_fixture():
    result = [m.model_dump(mode="json") for m in marks(Marks.model_validate(fixture("marks.json")))]

    assert result == [
        {
            "id": 10001,
            "date": "2026-10-20",
            "subject": {"id": 101, "name": "Алгебра"},
            "value": "9",
            "scale": "ten",
            "five": 4.5,
            "hundred": 90.0,
            "weight": 2,
            "control_form": "Контрольная работа",
            "comment": "Хорошо",
            "is_exam": False,
            "is_point": False,
            "point_date": None,
            "created_at": "2026-10-20T10:15:00+03:00",
            "ten": 9.0,
            "nmax": 10.0,
            "has_files": False,
            "updated_at": "2026-10-20T10:15:00+03:00",
            "criteria": [],
        },
        {
            "id": 10002,
            "date": "2026-10-21",
            "subject": {"id": 110, "name": "Физкультура"},
            "value": "зч",
            "scale": "pass_fail",
            "five": None,
            "hundred": None,
            "weight": 1,
            "control_form": "Зачёт",
            "comment": None,
            "is_exam": False,
            "is_point": True,
            "point_date": "2026-10-30",
            # Время без пояса дневник отдаёт по Москве.
            "created_at": "2026-10-21T12:00:00+03:00",
            # Нет пересчёта, файлов и правки — null, а не ошибка.
            "ten": None,
            "nmax": None,
            "has_files": None,
            "updated_at": None,
            "criteria": None,
        },
    ]


def test_scale_falls_back_to_original_grade_system():
    data = fixture("marks.json")
    data["payload"][0]["values"] = []

    [first, _] = marks(Marks.model_validate(data))

    assert first.scale == "ten"
    assert first.five is None


def test_mark_detail_literal_values():
    from diarysdk._api.raw import MarkInfo
    from diarysdk._mapping.marks import mark_detail

    result = mark_detail(MarkInfo.model_validate(fixture("mark_info.json"))).model_dump(mode="json")

    assert result == {
        "id": 10001,
        "value": "9",
        "five": 4.5,
        "weight": 2,
        "control_form": "Контрольная работа",
        "comment": "Хорошо",
        "is_exam": False,
        "is_point": False,
        "point_date": None,
        "date": "2026-10-20",
        "teacher": {"last_name": "Учителева", "first_name": "Анна", "middle_name": "Петровна"},
        "lesson": {"topic": "Квадратные уравнения", "schedule_item_id": 20001},
        "class_results": {
            "total_students": 25,
            "distribution": [
                {"value": "9", "students": 4, "percent": 16},
                {"value": "8", "students": 10, "percent": 40},
            ],
        },
        "criteria": [],
        "history": [{"value": "8", "changed_at": "2026-10-20T11:00:00+03:00"}],
        "result_files": [],
    }


def test_mark_detail_without_optional_parts_is_nulls():
    from diarysdk._api.raw import MarkInfo
    from diarysdk._mapping.marks import mark_detail

    result = mark_detail(MarkInfo.model_validate({"id": 5})).model_dump(mode="json")

    assert result["id"] == 5
    assert result["teacher"] is None
    assert result["lesson"] is None
    assert result["class_results"] is None
    assert result["criteria"] is None


def test_mark_detail_class_results_carry_no_identifiers():
    from diarysdk._api.raw import MarkInfo
    from diarysdk._mapping.marks import mark_detail

    data = fixture("mark_info.json")
    data["class_results"]["distribution"][0].update(person_id=7, student_id=8, names=["Иванов"])

    dumped = mark_detail(MarkInfo.model_validate(data)).class_results.model_dump(mode="json")

    assert set(dumped["distribution"][0]) == {"value", "students", "percent"}
