import datetime as dt

from pydantic import Field, JsonValue

from diarysdk.models.common import Schema


class CurriculumSubjectWeek(Schema):
    """Часы предмета в неделю учебного года."""

    week_number: int | None = None
    hours: int | None = None


class CurriculumSubject(Schema):
    subject_id: int | None = None
    subject_name: str | None = None
    # Родительский предмет (например, у подпредмета раздела).
    parent_subject_id: int | None = None
    total_hours: int | None = None
    passed_hours: int | None = None
    min_hours_per_week: int | None = None
    max_hours_per_week: int | None = None
    teachers: list[str] = Field(default_factory=list)
    weeks: list[CurriculumSubjectWeek] = Field(default_factory=list)


class CurriculumSection(Schema):
    """Раздел плана: область знаний и её предметы."""

    knowledge_field: str | None = None
    subjects: list[CurriculumSubject] = Field(default_factory=list)


class CurriculumWeek(Schema):
    week_number: int | None = None
    begin: dt.date | None = None
    end: dt.date | None = None
    hours: int | None = None
    days: int | None = None


class Curriculum(Schema):
    """Учебный план параллели. Форма уточняется по живому ответу."""

    title: str | None = None
    short_name: str | None = None
    education_level: str | None = None
    education_form: str | None = None
    class_level_id: int | None = None
    hours: int | None = None
    days_in_week: int | None = None
    is_adapted: bool | None = None
    # Форма неизвестна: отдаётся как пришло, пока живой ответ не покажет её.
    comments: JsonValue = None
    specialization: JsonValue = None
    study_profile: JsonValue = None
    sections: list[CurriculumSection] = Field(default_factory=list)
    weeks: list[CurriculumWeek] = Field(default_factory=list)
