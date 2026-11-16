from diarysdk._mapping.schedule import schedule
from diarysdk._wire.web import EventsResponse
from tests.fakes import fixture


def mapped():
    events = EventsResponse.model_validate(fixture("events.json"))
    return [item.model_dump(mode="json") for item in schedule(events)]


def test_mark_criteria_stay_plain_json():
    # criteria выходят наружу теми же словарями, что пришли от дневника.
    data = fixture("events.json")
    data["response"][0]["marks"][0]["criteria"] = [{"name": "К1", "value": "2"}]

    [first, *_] = schedule(EventsResponse.model_validate(data))

    assert first.marks[0].criteria == [{"name": "К1", "value": "2"}]


def test_lesson_with_mark_and_homework():
    lesson = mapped()[0]

    assert {k: v for k, v in lesson.items() if k != "marks"} == {
        "id": 20001,
        "date": "2026-10-20",
        "start": "2026-10-20T08:30:00+03:00",
        "end": "2026-10-20T09:15:00+03:00",
        "subject": {"id": 101, "name": "Алгебра"},
        "room": "204",
        "lesson_type": "NORMAL",
        "is_cancelled": False,
        "homework": [
            {
                "text": "№ 1-5 стр. 10",
                "materials": [
                    {
                        "title": "Задание.pdf",
                        "url": "https://dnevnik.test/files/zadanie.pdf",
                        "description": None,
                        "content_type": None,
                        "type_name": None,
                        "action_name": None,
                    }
                ],
            }
        ],
        "health_status": "освобождён",
        "is_missed": False,
        "absence_reason_id": 13,
        "nonattendance_reason_id": 1,
        "is_replaced": False,
        "replaced_teacher_id": None,
        "link_to_join": None,
        "lesson_form": None,
        "course_lesson_type": None,
        "source": "PLAN",
        # Строка, а не число: так в живом ответе (по наблюдениям).
        "source_id": "20001",
        "homework_counts": {"total": 1, "executed": 0, "presence_status_id": 1},
    }
    [mark] = lesson["marks"]
    assert mark["value"] == "9"
    assert mark["five"] == 4.5
    # У оценок календаря нет своей даты — это дата урока.
    assert mark["date"] == "2026-10-20"
    assert mark["subject"] == {"id": 101, "name": "Алгебра"}


def test_cancelled_lesson_without_timezone_and_with_plain_homework():
    lesson = mapped()[1]

    assert lesson["start"] == "2026-10-20T09:25:00+03:00"
    assert lesson["room"] == "Лаборатория"
    assert lesson["is_cancelled"] is True
    assert lesson["homework"] == [{"text": "Повторить § 3", "materials": []}]


def test_event_without_subject():
    event = mapped()[2]

    assert event["subject"] is None
    assert event["room"] is None
    assert event["marks"] == []
    assert event["homework"] == []
    assert event["source"] == "EC"
    assert event["homework_counts"] is None


def test_lesson_form_goes_as_is():
    data = fixture("events.json")
    data["response"][0]["lesson_form"] = {"id": 3, "name": "дистанционно"}

    [first, *_] = schedule(EventsResponse.model_validate(data))

    assert first.lesson_form == {"id": 3, "name": "дистанционно"}
