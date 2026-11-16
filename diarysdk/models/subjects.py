from datetime import date

from pydantic import Field

from diarysdk.models.common import Schema, Subject
from diarysdk.models.marks import Mark


class TargetPath(Schema):
    """Один путь к цели: remain оценок value весом weight."""

    value: int | None = None
    weight: int | None = None
    remain: int | None = None


class Target(Schema):
    """Цель периода из дневника: оценка value, до неё remain оценок."""

    value: int | None = None
    round: str | None = None
    remain: int | None = None
    paths: list[TargetPath] = Field(default_factory=list)


class Period(Schema):
    title: str | None = None
    start: date | None = None
    end: date | None = None
    # Средний за период, пятибалльный; без оценок — null.
    average: float | None = None
    final_mark: str | None = None
    marks: list[Mark] = Field(default_factory=list)
    marks_count: int | None = None
    dynamic: str | None = None
    target: Target | None = None


class SubjectSummary(Schema):
    subject: Subject
    # average_by_all дневника: средний самого ученика по всем оценкам года, в
    # пятибалльной шкале. Это не средний класса, хотя по названию похоже.
    average: float | None = None
    dynamic: str | None = None
    year_mark: str | None = None
    periods: list[Period] = Field(default_factory=list)


class SubjectDetailPeriod(Schema):
    """Период из ответа по одному предмету: поля дневника как есть."""

    title: str | None = None
    start: date | None = None
    end: date | None = None
    # Средний за период строкой, как в дневнике («4.50»); без оценок — «0.00».
    value: str | None = None
    # Итоговая оценка периода, если выставлена.
    fixed_value: str | None = None
    dynamic: str | None = None
    count: int | None = None
    # До какой оценки и сколько каких оценок осталось: ради этого источник и берётся.
    target: Target | None = None
    marks: list[Mark] = Field(default_factory=list)


class SubjectDetail(Schema):
    subject_id: int | None = None
    subject_name: str | None = None
    # Поле average дневника, пятибалльное: строка разбирается в число, как и
    # средние в /v1/subjects (перевода из десятибалльной шкалы нет — дневник
    # отдаёт его уже в пяти баллах); «0.00» и не число — null.
    average_five: float | None = None
    # Средний по всем оценкам года, тоже пятибалльный.
    average_by_all: float | None = None
    dynamic: str | None = None
    periods: list[SubjectDetailPeriod] = Field(default_factory=list)
