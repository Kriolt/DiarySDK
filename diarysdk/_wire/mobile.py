"""Ответы мобильного семейства (family/mobile/v1/*): оценки, предметы, школа,
уведомления, периоды, учебный план и группа настроек."""

from typing import Any

from diarysdk._wire.common import DT, Wire


class Mark(Wire):
    """Оценка в списке оценок, предметов и календаре; values — как пришли."""

    id: int | None = None
    value: str | None = None
    values: Any = None
    comment: str | None = None
    weight: int | None = None
    point_date: DT | None = None
    control_form_name: str | None = None
    created_at: DT | None = None
    updated_at: DT | None = None
    criteria: Any = None
    date: DT | None = None
    is_exam: bool | None = None
    is_point: bool | None = None
    original_grade_system_type: str | None = None


class MarkItem(Mark):
    subject_name: str | None = None
    subject_id: int | None = None


class Marks(Wire):
    payload: list[MarkItem] | None = None


class TargetPath(Wire):
    value: int | None = None
    remain: int | None = None
    weight: int | None = None


class Target(Wire):
    value: int | None = None
    remain: int | None = None
    round: str | None = None
    paths: list[TargetPath] | None = None


class Period(Wire):
    start: DT | None = None
    end: DT | None = None
    start_iso: str | None = None
    end_iso: str | None = None
    title: str | None = None
    dynamic: str | None = None
    value: str | None = None
    marks: list[Mark] | None = None
    count: int | None = None
    target: Target | None = None
    fixed_value: str | int | None = None


class SubjectItem(Wire):
    dynamic: str | None = None
    periods: list[Period] | None = None
    subject_name: str | None = None
    subject_id: int | None = None
    average_by_all: str | None = None
    year_mark: Any = None


class SubjectsMarks(Wire):
    payload: list[SubjectItem] | None = None


class SubjectMarksForSubject(Wire):
    average: str | None = None
    dynamic: str | None = None
    periods: list[Period] | None = None
    subject_name: str | None = None
    subject_id: int | None = None
    average_by_all: str | None = None


class ClassroomTeacher(Wire):
    last_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None


class SchoolAddress(Wire):
    county: str | None = None
    district: str | None = None
    address: str | None = None


class SchoolTeacher(ClassroomTeacher):
    subject_names: list[str] | None = None


class Branch(Wire):
    name: str | None = None
    type: str | None = None
    address: str | None = None
    is_main_building: bool | None = None
    is_student_building: bool | None = None


class SchoolInfo(Wire):
    id: int | None = None
    name: str | None = None
    type: str | None = None
    principal: str | None = None
    classroom_teachers: list[ClassroomTeacher] | None = None
    address: SchoolAddress | None = None
    phone: str | None = None
    email: str | None = None
    website_link: str | None = None
    teachers: list[SchoolTeacher] | None = None
    branches: list[Branch] | None = None


class Notification(Wire):
    datetime: DT | None = None
    event_type: str | None = None
    subject_name: str | None = None
    new_hw_description: str | None = None
    teacher_name: str | None = None
    new_date_assigned_on: str | None = None
    new_date_prepared_for: str | None = None
    author_profile_id: int | None = None
    lesson_date: str | None = None
    old_mark_value: str | None = None
    new_mark_value: str | None = None
    new_is_exam: bool | None = None
    new_mark_weight: int | None = None
    control_form_name: str | None = None


class PeriodsSchedules(Wire):
    date: DT | None = None
    type: str | None = None
    title: str | None = None
    description: str | None = None
    events: Any = None


class CurriculumLoad(Wire):
    hours: int | None = None
    week_number: int | None = None


class CurriculumSubject(Wire):
    subject_name: str | None = None
    subject_id: int | None = None
    total_hours: int | None = None
    passed_hours: int | None = None
    max_hours_per_week: int | None = None
    min_hours_per_week: int | None = None
    teachers: list[str] | None = None
    loads: list[CurriculumLoad] | None = None
    parent_subject_id: int | None = None


class CurriculumSection(Wire):
    knowledge_field_name: str
    subjects: list[CurriculumSubject]


class WeekHours(Wire):
    hours: int | None = None
    days: int | None = None
    week_number: int | None = None
    begin_date: DT | None = None
    end_date: DT | None = None


class ParallelCurriculum(Wire):
    title: str | None = None
    hours: int | None = None
    comments: Any = None
    specialization: Any = None
    sections: list[CurriculumSection] | None = None
    short_name: str | None = None
    education_level: str | None = None
    days_in_week: int | None = None
    education_form: str | None = None
    class_level_id: int | None = None
    study_profile: Any = None
    is_adapted: bool | None = None
    week_hours: list[WeekHours] | None = None


class Theme(Wire):
    type: str | None = None
    is_automatic: bool | None = None
    color_pattern: str | None = None


class UserSettings(Wire):
    goal: bool | None = None
    theme: Theme | None = None
    schedule_type: str | None = None
    estimation_type: str | None = None
