"""/v1/subjects из family/mobile/v1/subject_marks."""

from diarysdk._mapping.common import as_date, as_text, average
from diarysdk._mapping.marks import mark
from diarysdk._wire.mobile import SubjectMarksForSubject, SubjectsMarks
from diarysdk.models.common import Subject
from diarysdk.models.subjects import (
    Period,
    SubjectDetail,
    SubjectDetailPeriod,
    SubjectSummary,
    Target,
    TargetPath,
)


def _target(target) -> Target | None:
    if target is None:
        return None
    return Target(
        value=target.value,
        round=target.round,
        remain=target.remain,
        paths=[
            TargetPath(value=path.value, weight=path.weight, remain=path.remain)
            for path in target.paths or []
        ],
    )


def subjects(data: SubjectsMarks) -> list[SubjectSummary]:
    result = []
    for item in data.payload or []:
        subject = Subject(id=item.subject_id, name=item.subject_name)
        result.append(
            SubjectSummary(
                subject=subject,
                # Собственное поле дневника average не отдаём: в октябре оно
                # у всех предметов 0.00 (по наблюдениям).
                average=average(item.average_by_all),
                dynamic=item.dynamic,
                year_mark=as_text(item.year_mark),
                periods=[
                    Period(
                        title=period.title,
                        start=as_date(period.start_iso or period.start),
                        end=as_date(period.end_iso or period.end),
                        average=average(period.value),
                        final_mark=as_text(period.fixed_value),
                        marks=[mark(m, subject) for m in period.marks or []],
                        marks_count=period.count,
                        dynamic=period.dynamic,
                        target=_target(period.target),
                    )
                    for period in item.periods or []
                ],
            )
        )
    return result


def subject_detail(data: SubjectMarksForSubject) -> SubjectDetail:
    """/v1/subjects/{id} из family/mobile/v1/subject_marks/for_subject.

    average_five — поле average дневника: пятибалльный средний строкой, в
    число его переводит то же average(), что и средние в /v1/subjects (из
    десятибалльной шкалы здесь ничего не пересчитывается). «0.00» и не число —
    null.
    """
    subject = Subject(id=data.subject_id, name=data.subject_name)
    return SubjectDetail(
        subject_id=data.subject_id,
        subject_name=data.subject_name,
        average_five=average(data.average),
        average_by_all=average(data.average_by_all),
        dynamic=data.dynamic,
        periods=[
            SubjectDetailPeriod(
                title=period.title,
                start=as_date(period.start),
                end=as_date(period.end),
                value=as_text(period.value),
                fixed_value=as_text(period.fixed_value),
                dynamic=period.dynamic,
                count=period.count,
                target=_target(period.target),
                marks=[mark(m, subject) for m in period.marks or []],
            )
            for period in data.periods or []
        ],
    )
