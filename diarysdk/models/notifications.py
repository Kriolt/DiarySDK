import datetime as dt

from diarysdk.models.common import Schema


class NotificationMark(Schema):
    """Оценка из записи ленты: что было и что стало."""

    old: str | None = None
    new: str | None = None
    weight: int | None = None
    is_exam: bool | None = None
    control_form: str | None = None


class NotificationHomework(Schema):
    """ДЗ из записи ленты: новое описание и даты."""

    description: str | None = None
    assigned_on: dt.date | None = None
    due: dt.date | None = None


class Notification(Schema):
    """Запись ленты дневника: что поменялось в оценках и ДЗ. Форма уточняется по живому ответу."""

    at: dt.datetime | None = None
    # Как пришёл из дневника, справочника значений нет.
    event_type: str | None = None
    subject_name: str | None = None
    teacher_name: str | None = None
    author_profile_id: int | None = None
    lesson_date: dt.date | None = None
    # Есть, если в записи пришло хоть одно поле оценки.
    mark: NotificationMark | None = None
    # Есть, если в записи пришло хоть одно поле ДЗ.
    homework: NotificationHomework | None = None
