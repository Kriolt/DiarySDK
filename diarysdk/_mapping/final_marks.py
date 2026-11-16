"""/v1/final-marks из family/web/v1/final_marks/v2 (свой запрос).

Форма — по живому ответу: {"subjects": [{id, name, periods, year_mark,
intermediate_attestation_mark, training_camp_mark}]}. periods во всех годах
пустые, их форма неизвестна — наружу не отдаём.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from diarysdk._mapping.common import as_text
from diarysdk.errors import UpstreamFormat
from diarysdk.models.common import Subject
from diarysdk.models.marks import FinalMark


class _Subject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None
    year_mark: Any = None
    intermediate_attestation_mark: Any = None
    training_camp_mark: Any = None


class _Answer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subjects: list[_Subject]


def final_marks(data: Any) -> list[FinalMark]:
    try:
        answer = _Answer.model_validate(data)
    except ValidationError as error:
        raise UpstreamFormat.from_validation(error) from None
    return [
        FinalMark(
            subject=Subject(id=item.id, name=item.name),
            year_mark=as_text(item.year_mark),
            attestation_mark=as_text(item.intermediate_attestation_mark),
            training_camp_mark=as_text(item.training_camp_mark),
        )
        for item in answer.subjects
    ]
