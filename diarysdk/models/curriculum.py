import datetime as dt

from pydantic import Field, JsonValue

from diarysdk.models.common import Schema, Subject


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


class ProgramLesson(Schema):
    """Урок рабочей программы; `lesson_id` — для `lesson()`, если урок уже в расписании."""

    title: str | None = None
    ordinal: int | None = None
    date: dt.date | None = None
    lesson_id: int | None = None
    oge_tasks: list[str] = Field(default_factory=list)
    ege_tasks: list[str] = Field(default_factory=list)


class ProgramTopic(Schema):
    title: str | None = None
    ordinal: int | None = None
    lessons: list[ProgramLesson] = Field(default_factory=list)


class ProgramModule(Schema):
    """Раздел рабочей программы группы (сайт: «Рабочие программы»)."""

    title: str | None = None
    ordinal: int | None = None
    subject_id: int | None = None
    topics: list[ProgramTopic] = Field(default_factory=list)


class TopicResult(Schema):
    """Ожидаемый результат по теме; `text` — формулировка для семьи."""

    id: int | None = None
    text: str | None = None
    type: str | None = None
    mandatory: str | None = None


class SubjectTopic(Schema):
    """Тема предмета (тематическая рамка) и её результаты."""

    id: int | None = None
    title: str | None = None
    results: list[TopicResult] = Field(default_factory=list)


class ControlWork(Schema):
    """Контрольная работа. Форма не подтверждена: живые ответы были пустыми,
    поля — по тому, что читает сайт («Контрольные работы»)."""

    date: dt.date | None = None
    subject: Subject
    form: str | None = None
    theme: str | None = None
    lesson_id: int | None = None
    mark: str | None = None
    is_absent: bool | None = None
    is_success: bool | None = None
