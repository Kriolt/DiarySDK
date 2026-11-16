"""/v1/exams из portfolio/app/persons/{guid}/govexams/list/ (свой запрос).

Форма ответа известна только по одному клиенту, поэтому модель лояльная:
принимает список или объект со списком и несколько написаний ключей. Это
догадки до живого ответа — по её живому ответу модель сузится до настоящих полей.
"""

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from diarysdk._mapping.common import as_date, as_text
from diarysdk.errors import UpstreamFormat
from diarysdk.models.exams import Exam


class _Exam(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str | None = Field(None, validation_alias=AliasChoices("exam_type", "examType", "kind"))
    subject: str | None = Field(
        None, validation_alias=AliasChoices("subject", "subject_name", "subjectName")
    )
    date: Any = Field(None, validation_alias=AliasChoices("date", "exam_date", "examDate"))
    score: int | float | None = Field(
        None, validation_alias=AliasChoices("score", "test_score", "testScore", "result")
    )
    mark: Any = Field(None, validation_alias=AliasChoices("mark", "grade"))


class _Answer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[_Exam] | None = Field(None, validation_alias=AliasChoices("data", "payload"))


def exams(data: Any) -> list[Exam]:
    if isinstance(data, list):
        data = {"data": data}
    try:
        answer = _Answer.model_validate(data)
    except ValidationError as error:
        raise UpstreamFormat.from_validation(error) from None
    return [
        Exam(
            kind=item.kind,
            subject=item.subject,
            date=as_date(item.date),
            score=item.score,
            mark=as_text(item.mark),
        )
        for item in answer.items or []
    ]
