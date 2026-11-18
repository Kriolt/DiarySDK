"""Ответы журнала ej/core/family: только читаемые поля, остальное — extra."""

from typing import Any

from diarysdk._wire.common import Wire


class EjSubject(Wire):
    id: int | None = None
    name: str | None = None


class EjTeacher(Wire):
    id: int | None = None
    name: str | None = None
    type: str | None = None
    roles: list[str] | None = None
    subjects: list[EjSubject] | None = None


class DebtFinalMark(Wire):
    value: Any = None


class DebtAttempt(Wire):
    academic_debt_final_mark: DebtFinalMark | None = None


class EjAcademicDebt(Wire):
    student_profile_id: int | None = None
    subject_id: int | None = None
    subject_name: str | None = None
    original_final_mark: Any = None
    academic_debt_attempts: list[DebtAttempt] | None = None
