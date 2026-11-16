"""/v1/lessons/{id} из family/mobile/v1/lesson_schedule_items/{id}.

Ответ разбирается лояльной моделью: пересчёт оценки в пятибалльную шкалу —
дробное число, и десятибалльная «9» (4.5) не роняет урок.
Модель описывает только поля, которые мы отдаём.
"""

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from diarysdk._clock import MOSCOW
from diarysdk._mapping.common import as_date, as_float, as_json, materials
from diarysdk._mapping.marks import mark
from diarysdk.errors import UpstreamFormat
from diarysdk.models.common import Material, Subject
from diarysdk.models.lessons import Lesson, LessonTeacher, Theme
from diarysdk.models.schedule import HomeworkBrief


class _In(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Grade(_In):
    five: float | None = None
    hundred: float | None = None
    ten: float | None = None


class _Value(_In):
    grade_system_type: str | None = None
    nmax: float | None = None
    grade: _Grade | None = None


class _Mark(_In):
    id: int | None = None
    value: str | None = None
    values: list[_Value] | None = None
    weight: int | None = None
    control_form_name: str | None = None
    comment: str | None = None
    is_exam: bool | None = None
    is_point: bool | None = None
    point_date: Any = None
    created_at: Any = None
    updated_at: Any = None
    has_files: bool | None = None
    criteria: Any = None
    original_grade_system_type: str | None = None


class _Teacher(_In):
    last_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    sex: str | None = None
    birth_date: Any = None
    user_id: int | None = None


class _Theme(_In):
    id: int | None = None
    title: str | None = None
    average_mark: Any = None
    oge_task_name: Any = None
    ege_task_name: Any = None
    theme_frames: list[_Theme] | None = None


class _Url(_In):
    url: str | None = None


class _Item(_In):
    title: str | None = None
    link: str | None = None
    urls: list[_Url] | None = None


class _MaterialGroup(_In):
    type_name: str | None = None
    action_name: str | None = None
    items: list[_Item] | None = None


class _Homework(_In):
    homework: str | None = None
    materials: list[_MaterialGroup] | None = None


class _Details(_In):
    lesson_topic: str | None = None
    materials: list[Any] | None = None
    theme: _Theme | None = None
    content: Any = None


class _Lesson(_In):
    id: int | None = None
    date: Any = None
    begin_time: str | None = None
    end_time: str | None = None
    subject_id: int | None = None
    subject_name: str | None = None
    teacher: _Teacher | None = None
    room_number: str | None = None
    room_name: str | None = None
    marks: list[_Mark] | None = None
    lesson_homeworks: list[_Homework] | None = None
    details: _Details | None = None
    is_missed_lesson: bool | None = None
    nonattendance_reason_id: int | None = None
    building_name: str | None = None
    comment: str | None = None
    is_virtual: bool | None = None
    lesson_type: str | None = None
    lesson_education_type: str | None = None
    plan_id: int | None = None
    group_id: int | None = None
    # Форма по наблюдениям не видна — как пришли.
    disease_status_type: Any = None
    remote_lesson: Any = None
    control: Any = None
    evaluation: Any = None
    teacher_comments: Any = None
    student_work: Any = None
    theme_mastery: Any = None
    kr_attachments: Any = None


def _theme(theme: _Theme | None) -> Theme | None:
    if theme is None:
        return None
    return Theme(
        id=theme.id,
        title=theme.title,
        average_mark=as_float(theme.average_mark),
        oge_task=theme.oge_task_name,
        ege_task=theme.ege_task_name,
        frames=[_theme(frame) for frame in theme.theme_frames or []],
    )


def _at(day: date | None, clock_time: str | None) -> datetime | None:
    if day is None or not clock_time:
        return None
    try:
        return datetime.combine(day, time.fromisoformat(clock_time), MOSCOW)
    except ValueError:
        return None


def _homework_materials(groups: list[_MaterialGroup] | None) -> list[Material]:
    # Вид и действие у урока заданы на группу материалов, а не на каждый.
    return [
        Material(
            title=item.title,
            url=(item.urls[0].url if item.urls else None) or item.link,
            type_name=group.type_name,
            action_name=group.action_name,
        )
        for group in groups or []
        for item in group.items or []
    ]


def lesson(data: Any) -> Lesson:
    try:
        item = _Lesson.model_validate(data)
    except ValidationError as error:
        raise UpstreamFormat.from_validation(error) from None
    day = as_date(item.date)
    subject = (
        Subject(id=item.subject_id, name=item.subject_name)
        if item.subject_id is not None or item.subject_name
        else None
    )
    teacher = item.teacher
    return Lesson(
        id=item.id,
        date=day,
        start=_at(day, item.begin_time),
        end=_at(day, item.end_time),
        subject=subject,
        room=item.room_number or item.room_name,
        topic=item.details.lesson_topic if item.details else None,
        teacher=(
            LessonTeacher(
                last_name=teacher.last_name,
                first_name=teacher.first_name,
                middle_name=teacher.middle_name,
                sex=teacher.sex,
                birth_date=as_date(teacher.birth_date),
                user_id=teacher.user_id,
            )
            if teacher
            else None
        ),
        marks=[mark(m, subject, day) for m in item.marks or []],
        homework=[
            HomeworkBrief(text=h.homework, materials=_homework_materials(h.materials))
            for h in item.lesson_homeworks or []
        ],
        materials=materials(item.details.materials) if item.details else [],
        is_missed=item.is_missed_lesson,
        nonattendance_reason_id=item.nonattendance_reason_id,
        building=item.building_name,
        comment=item.comment,
        is_virtual=item.is_virtual,
        lesson_type=item.lesson_type,
        lesson_education_type=item.lesson_education_type,
        plan_id=item.plan_id,
        group_id=item.group_id,
        theme=_theme(item.details.theme) if item.details else None,
        disease_status=as_json(item.disease_status_type),
        is_remote=as_json(item.remote_lesson),
        control=as_json(item.control),
        evaluation=as_json(item.evaluation),
        teacher_comments=as_json(item.teacher_comments),
        student_work=as_json(item.student_work),
        theme_mastery=as_json(item.theme_mastery),
        kr_attachments=as_json(item.kr_attachments),
        content=as_json(item.details.content) if item.details else None,
    )
