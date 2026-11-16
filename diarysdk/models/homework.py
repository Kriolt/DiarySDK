from datetime import date, datetime

from pydantic import Field, JsonValue

from diarysdk.models.common import Material, Schema, Subject


class Attachment(Schema):
    name: str | None = None
    url: str | None = None


class Homework(Schema):
    # Только homework_entry_student_id: именно его принимает отметка выполнения;
    # None — дневник его не дал, отметить такое ДЗ нельзя.
    id: int | None = None
    # Дата сдачи — по ней задаётся период /v1/homework.
    due: date | None = None
    assigned_on: date | None = None
    subject: Subject | None = None
    text: str | None = None
    materials: list[Material] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    is_done: bool | None = None
    has_teacher_answer: bool | None = None
    type: str | None = None
    group_id: int | None = None
    homework_id: int | None = None
    entry_id: int | None = None
    # Начало урока, к которому задано.
    lesson_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Как пришли: в наблюдениях всегда пустые, форма не подтверждена.
    comments: JsonValue = None
    written_answer: JsonValue = None
