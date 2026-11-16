"""/v1/schedule из eventcalendar/v1/api/events.

Календарь запрашивается с полным expand, поэтому в событиях есть
health_status и причины пропусков; они отдаются как есть, кодами дневника.
"""

from diarysdk._clock import MOSCOW
from diarysdk._mapping.common import as_datetime, as_json, field, materials
from diarysdk._mapping.marks import mark
from diarysdk._wire.web import EventsResponse
from diarysdk.models.common import Subject
from diarysdk.models.schedule import HomeworkBrief, HomeworkCounts, ScheduleItem


def _homework(homework) -> list[HomeworkBrief]:
    if homework is None:
        return []
    if homework.entries:
        return [
            HomeworkBrief(text=entry.description, materials=materials(entry.attachments))
            for entry in homework.entries
        ]
    return [HomeworkBrief(text=text) for text in homework.descriptions or []]


def _homework_counts(homework) -> HomeworkCounts | None:
    if homework is None:
        return None
    return HomeworkCounts(
        total=homework.total_count,
        executed=homework.execute_count,
        presence_status_id=homework.presence_status_id,
    )


def schedule(events: EventsResponse) -> list[ScheduleItem]:
    result = []
    for item in events.response or []:
        start = as_datetime(item.start_at)
        day = start.astimezone(MOSCOW).date() if start else None
        subject = (
            Subject(id=item.subject_id, name=item.subject_name)
            if item.subject_id is not None or item.subject_name
            else None
        )
        result.append(
            ScheduleItem(
                id=item.id,
                date=day,
                start=start,
                end=as_datetime(item.finish_at),
                subject=subject,
                room=item.room_number or item.room_name,
                lesson_type=item.lesson_type,
                is_cancelled=item.cancelled,
                marks=[mark(m, subject, day) for m in item.marks or []],
                homework=_homework(item.homework),
                health_status=item.health_status,
                is_missed=item.is_missed_lesson,
                absence_reason_id=item.absence_reason_id,
                nonattendance_reason_id=item.nonattendance_reason_id,
                is_replaced=item.replaced,
                replaced_teacher_id=item.replaced_teacher_id,
                link_to_join=item.link_to_join,
                # lesson_form модель ответа не объявляет.
                lesson_form=as_json(field(item, "lesson_form")),
                course_lesson_type=item.course_lesson_type,
                source=item.source,
                source_id=item.source_id,
                homework_counts=_homework_counts(item.homework),
            )
        )
    return result
