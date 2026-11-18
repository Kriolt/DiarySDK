"""Журнал ej/core/family → публичные модели."""

from typing import Any

from pydantic import TypeAdapter, ValidationError

from diarysdk._mapping.common import as_json
from diarysdk._wire.ej import EjAcademicDebt, EjTeacher
from diarysdk.errors import UpstreamFormat
from diarysdk.models.common import Subject
from diarysdk.models.marks import AcademicDebt
from diarysdk.models.school import SchoolTeacher

_TEACHERS = TypeAdapter(list[EjTeacher])
_DEBTS = TypeAdapter(list[EjAcademicDebt])


def _parse[T](adapter: TypeAdapter[T], data: Any) -> T:
    try:
        return adapter.validate_python(data)
    except ValidationError as error:
        raise UpstreamFormat.from_validation(error) from None


def teachers(data: Any) -> list[SchoolTeacher]:
    return [
        SchoolTeacher(
            id=item.id,
            name=item.name,
            type=item.type,
            roles=list(item.roles or []),
            subjects=[Subject(id=s.id, name=s.name) for s in item.subjects or []],
        )
        for item in _parse(_TEACHERS, data)
        if item.id is not None
    ]


def academic_debts(data: Any, student_id: int) -> list[AcademicDebt]:
    """Долги ученика. Дневник отвечает по классу: чужие строки и строки без
    ученика отбрасываются — иначе наружу ушли бы данные одноклассников."""
    result = []
    for item in _parse(_DEBTS, data):
        if item.student_profile_id != student_id:
            continue
        attempts = item.academic_debt_attempts or []
        attested = bool(item.original_final_mark) or any(
            a.academic_debt_final_mark is not None and a.academic_debt_final_mark.value
            for a in attempts
        )
        raw = [a.model_dump(mode="json") for a in attempts] if attempts else None
        result.append(
            AcademicDebt(
                subject=Subject(id=item.subject_id, name=item.subject_name),
                original_final_mark=as_json(item.original_final_mark),
                attested=attested,
                attempts=raw,
            )
        )
    return result
