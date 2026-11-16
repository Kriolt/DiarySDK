"""/v1/curriculum из family/mobile/v1/programs/parallel_curriculum/{id}.

subject_integration_id и loads[].id — внутренние ID дневника, не берём.
"""

from diarysdk._mapping.common import as_date, as_json
from diarysdk._wire.mobile import ParallelCurriculum
from diarysdk.models.curriculum import (
    Curriculum,
    CurriculumSection,
    CurriculumSubject,
    CurriculumSubjectWeek,
    CurriculumWeek,
)


def curriculum(data: ParallelCurriculum) -> Curriculum:
    return Curriculum(
        title=data.title,
        short_name=data.short_name,
        education_level=data.education_level,
        education_form=data.education_form,
        class_level_id=data.class_level_id,
        hours=data.hours,
        days_in_week=data.days_in_week,
        is_adapted=data.is_adapted,
        comments=as_json(data.comments),
        specialization=as_json(data.specialization),
        study_profile=as_json(data.study_profile),
        sections=[
            CurriculumSection(
                knowledge_field=section.knowledge_field_name,
                subjects=[
                    CurriculumSubject(
                        subject_id=subject.subject_id,
                        subject_name=subject.subject_name,
                        parent_subject_id=subject.parent_subject_id,
                        total_hours=subject.total_hours,
                        passed_hours=subject.passed_hours,
                        min_hours_per_week=subject.min_hours_per_week,
                        max_hours_per_week=subject.max_hours_per_week,
                        teachers=subject.teachers or [],
                        weeks=[
                            CurriculumSubjectWeek(week_number=load.week_number, hours=load.hours)
                            for load in subject.loads or []
                        ],
                    )
                    for subject in section.subjects
                ],
            )
            for section in data.sections or []
        ],
        weeks=[
            CurriculumWeek(
                week_number=week.week_number,
                begin=as_date(week.begin_date),
                end=as_date(week.end_date),
                hours=week.hours,
                days=week.days,
            )
            for week in data.week_hours or []
        ],
    )
