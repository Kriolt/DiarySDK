"""Оценка дневника → схема Mark.

Оценки приходят из нескольких ответов (оценки, предметы, календарь, урок) с
почти одинаковыми полями, но где-то values — модели, а где-то сырые словари.
"""

from datetime import date
from typing import Any

from diarysdk._api.raw import MarkInfo
from diarysdk._mapping.common import as_date, as_datetime, as_float, as_json, as_text, field
from diarysdk._wire.mobile import Marks
from diarysdk.models.common import PersonName, Subject
from diarysdk.models.marks import (
    ClassResults,
    Mark,
    MarkDetail,
    MarkDistribution,
    MarkLesson,
)


def mark(item: Any, subject: Subject | None, on: date | None = None) -> Mark:
    """on — дата урока для оценок без своей даты (календарь, урок)."""
    values = field(item, "values") or []
    first = values[0] if isinstance(values, list) and values else None
    grade = field(first, "grade")
    return Mark(
        id=field(item, "id"),
        date=as_date(field(item, "date")) or on,
        subject=subject,
        value=field(item, "value"),
        scale=field(first, "grade_system_type") or field(item, "original_grade_system_type"),
        five=as_float(field(grade, "five")),
        hundred=as_float(field(grade, "hundred")),
        weight=field(item, "weight"),
        control_form=field(item, "control_form_name"),
        comment=field(item, "comment"),
        is_exam=field(item, "is_exam"),
        is_point=field(item, "is_point"),
        point_date=as_date(field(item, "point_date")),
        created_at=as_datetime(field(item, "created_at")),
        ten=as_float(field(grade, "ten")),
        nmax=as_float(field(first, "nmax")),
        has_files=field(item, "has_files"),
        updated_at=as_datetime(field(item, "updated_at")),
        criteria=as_json(field(item, "criteria")),
    )


def marks(data: Marks) -> list[Mark]:
    """/v1/marks из family/mobile/v1/marks."""
    return [
        mark(item, Subject(id=item.subject_id, name=item.subject_name))
        for item in data.payload or []
    ]


def mark_detail(info: MarkInfo) -> MarkDetail:
    """/v1/marks/{id} из family/mobile/v1/marks/{id}.

    Оценка разбирается тем же mark(), что и в списке. class_results — только
    числа: что бы ни пришло рядом (ID, имена), в ответ не попадает.
    """
    base = mark(info, None)
    teacher, lesson, results = info.teacher, info.lesson, info.class_results
    return MarkDetail(
        id=base.id,
        value=base.value,
        five=base.five,
        weight=base.weight,
        control_form=base.control_form,
        comment=base.comment,
        is_exam=base.is_exam,
        is_point=base.is_point,
        point_date=base.point_date,
        date=base.date,
        teacher=None
        if teacher is None
        else PersonName(
            last_name=teacher.last_name,
            first_name=teacher.first_name,
            middle_name=teacher.middle_name,
        ),
        lesson=None
        if lesson is None
        else MarkLesson(topic=lesson.topic, schedule_item_id=lesson.schedule_item_id),
        class_results=None
        if results is None
        else ClassResults(
            total_students=results.total_students,
            distribution=[
                MarkDistribution(
                    value=as_text(item.value), students=item.students, percent=item.percent
                )
                for item in results.distribution or []
            ],
        ),
        criteria=as_json(info.criteria),
        history=as_json(info.history),
        result_files=as_json(info.result_files),
    )
