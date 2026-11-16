"""/v1/homework из family/mobile/v1/homeworks (свой запрос).

Полные ДЗ с материалами — свой запрос, а ответ разбирается лояльной моделью.
Форма ответа известна по другим клиентам; живой ответ покажет её, и тогда модель уточнится.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from diarysdk._mapping.common import as_date, as_datetime, materials
from diarysdk.errors import UpstreamFormat
from diarysdk.models.common import Subject
from diarysdk.models.homework import Attachment, Homework


class _Item(BaseModel):
    model_config = ConfigDict(extra="ignore")

    homework_entry_student_id: int | None = None
    homework_entry_id: int | None = None
    homework_id: int | None = None
    date: Any = None
    date_prepared_for: Any = None
    date_assigned_on: Any = None
    subject_id: int | None = None
    subject_name: str | None = None
    description: str | None = None
    homework: str | None = None
    materials: list[Any] | None = None
    attachments: list[Any] | None = None
    is_done: bool | None = None
    has_teacher_answer: bool | None = None
    type: str | None = None
    group_id: int | None = None
    lesson_date_time: Any = None
    homework_created_at: Any = None
    homework_updated_at: Any = None
    comments: Any = None
    written_answer: Any = None


class _Answer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    payload: list[_Item] | None = None


def _attachments(items: list[Any] | None) -> list[Attachment]:
    return [Attachment(name=m.title, url=m.url) for m in materials(items) if m.title or m.url]


def homework(data: Any) -> list[Homework]:
    if isinstance(data, list):
        data = {"payload": data}
    try:
        answer = _Answer.model_validate(data)
    except ValidationError as error:
        raise UpstreamFormat.from_validation(error) from None
    items = [
        Homework(
            # Только id из пространства записи; entry_id и homework_id — отдельные поля.
            id=item.homework_entry_student_id,
            due=as_date(item.date_prepared_for or item.date),
            assigned_on=as_date(item.date_assigned_on),
            subject=(
                Subject(id=item.subject_id, name=item.subject_name)
                if item.subject_id is not None or item.subject_name
                else None
            ),
            text=item.description or item.homework,
            materials=materials(item.materials),
            attachments=_attachments(item.attachments),
            is_done=item.is_done,
            has_teacher_answer=item.has_teacher_answer,
            type=item.type,
            group_id=item.group_id,
            homework_id=item.homework_id,
            entry_id=item.homework_entry_id,
            lesson_at=as_datetime(item.lesson_date_time),
            created_at=as_datetime(item.homework_created_at),
            updated_at=as_datetime(item.homework_updated_at),
            comments=item.comments,
            written_answer=item.written_answer,
        )
        for item in answer.payload or []
    ]
    # Порядок дневника зависит от хоста, поэтому свой: по сроку сдачи, затем
    # по предмету; без срока — в конце.
    return sorted(
        items,
        key=lambda h: (
            h.due is None,
            h.due or date.min,
            (h.subject.name if h.subject else None) or "",
            h.id or 0,
        ),
    )
