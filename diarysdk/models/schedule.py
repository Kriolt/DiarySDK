import datetime as dt

from pydantic import Field, JsonValue

from diarysdk.models.common import Material, Schema, Subject
from diarysdk.models.marks import Mark


class HomeworkBrief(Schema):
    text: str | None = None
    materials: list[Material] = Field(default_factory=list)


class HomeworkCounts(Schema):
    total: int | None = None
    executed: int | None = None
    presence_status_id: int | None = None


class ScheduleItem(Schema):
    """Урок или событие календаря. Подробности урока — /v1/lessons/{id}."""

    id: int | None = None
    date: dt.date | None = None
    start: dt.datetime | None = None
    end: dt.datetime | None = None
    subject: Subject | None = None
    room: str | None = None
    lesson_type: str | None = None
    is_cancelled: bool | None = None
    marks: list[Mark] = Field(default_factory=list)
    homework: list[HomeworkBrief] = Field(default_factory=list)
    health_status: str | None = None
    is_missed: bool | None = None
    # Коды дневника как есть.
    absence_reason_id: int | None = None
    nonattendance_reason_id: int | None = None
    is_replaced: bool | None = None
    replaced_teacher_id: int | None = None
    link_to_join: str | None = None
    # Как пришло: в наблюдениях всегда null, форма не подтверждена.
    lesson_form: JsonValue = None
    course_lesson_type: str | None = None
    # Откуда событие: PLAN — урок из расписания, EC — событие календаря.
    source: str | None = None
    source_id: str | None = None
    homework_counts: HomeworkCounts | None = None
