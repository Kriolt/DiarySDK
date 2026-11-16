import json

from diarysdk._mapping.notifications import notifications
from diarysdk._wire.mobile import Notification as LibNotification
from tests.fakes import fixture_text, wire_list


def mapped(data=None):
    text = fixture_text("notifications.json") if data is None else json.dumps(data)
    parsed = wire_list(LibNotification, text)
    return [n.model_dump(mode="json") for n in notifications(parsed)]


def test_newest_first_undated_last_with_literal_values():
    result = mapped()

    assert result == [
        {
            "at": "2026-10-22T16:00:00+03:00",
            "event_type": "create_homework",
            "subject_name": "Литература",
            "teacher_name": "Образцова Мария Петровна",
            "author_profile_id": 7102,
            "lesson_date": "2026-10-22",
            "mark": None,
            "homework": {
                "description": "Прочитать главу 5",
                "assigned_on": "2026-10-22",
                "due": "2026-10-26",
            },
        },
        {
            "at": "2026-10-20T10:20:00+03:00",
            "event_type": "create_mark",
            "subject_name": "Алгебра",
            "teacher_name": "Тестова Анна Ивановна",
            "author_profile_id": 7101,
            "lesson_date": "2026-10-20",
            "mark": {
                "old": None,
                "new": "9",
                "weight": 2,
                "is_exam": False,
                "control_form": "Контрольная работа",
            },
            "homework": None,
        },
        {
            "at": None,
            "event_type": "update_mark",
            "subject_name": "Черчение",
            "teacher_name": None,
            "author_profile_id": None,
            "lesson_date": None,
            "mark": {
                "old": "8",
                "new": "10",
                "weight": None,
                "is_exam": None,
                "control_form": None,
            },
            "homework": None,
        },
    ]


def test_service_fields_are_not_taken():
    text = str(mapped())

    assert "created_at" not in text
    assert "updated_at" not in text
    assert "student_profile_id" not in text
    assert "7001" not in text


def test_record_without_mark_and_homework_fields_has_neither():
    [item] = mapped([{"event_type": "other", "datetime": "2026-10-20T10:00:00+03:00"}])

    assert item["mark"] is None
    assert item["homework"] is None


def test_empty_list():
    assert mapped([]) == []
