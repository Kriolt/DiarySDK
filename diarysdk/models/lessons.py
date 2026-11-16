import datetime as dt

from pydantic import Field, JsonValue

from diarysdk.models.common import Material, PersonName, Schema, Subject
from diarysdk.models.marks import Mark
from diarysdk.models.schedule import HomeworkBrief


class LessonTeacher(PersonName):
    sex: str | None = None
    birth_date: dt.date | None = None
    user_id: int | None = None


class Theme(Schema):
    """Тема урока и вложенные разделы (theme_frames дневника, любой глубины)."""

    id: int | None = None
    title: str | None = None
    average_mark: float | None = None
    # Задания ОГЭ и ЕГЭ — как пришли: в наблюдении это то null, то список строк.
    oge_task: JsonValue = None
    ege_task: JsonValue = None
    frames: list[Theme] = Field(default_factory=list)


class Lesson(Schema):
    id: int | None = None
    date: dt.date | None = None
    start: dt.datetime | None = None
    end: dt.datetime | None = None
    subject: Subject | None = None
    room: str | None = None
    topic: str | None = None
    teacher: LessonTeacher | None = None
    marks: list[Mark] = Field(default_factory=list)
    homework: list[HomeworkBrief] = Field(default_factory=list)
    materials: list[Material] = Field(default_factory=list)
    is_missed: bool | None = None
    nonattendance_reason_id: int | None = None
    building: str | None = None
    comment: str | None = None
    is_virtual: bool | None = None
    lesson_type: str | None = None
    lesson_education_type: str | None = None
    plan_id: int | None = None
    group_id: int | None = None
    theme: Theme | None = None
    # Как пришли: в наблюдениях у двух учеников за 60 уроков всегда null или
    # пустые, форма не подтверждена.
    disease_status: JsonValue = None
    is_remote: JsonValue = None
    control: JsonValue = None
    evaluation: JsonValue = None
    teacher_comments: JsonValue = None
    student_work: JsonValue = None
    theme_mastery: JsonValue = None
    kr_attachments: JsonValue = None
    content: JsonValue = None
