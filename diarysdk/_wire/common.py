"""Основа моделей ответов и разбор тела ответа в модель."""

from datetime import date, datetime
from functools import cache
from typing import Any

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from diarysdk._transport import DiaryResponse
from diarysdk.errors import UpstreamFormat

# Дата или время, а что не разобралось, остаётся как пришло.
DT = datetime | date | Any


class Wire(BaseModel):
    """Незнакомые поля не выбрасываются: _mapping читает часть из них по ключам."""

    model_config = ConfigDict(extra="allow")


@cache
def _list_adapter[M: BaseModel](model: type[M]) -> TypeAdapter[list[M]]:
    return TypeAdapter(list[model])


def _text(response: DiaryResponse) -> str:
    text = response.text()
    if not text:
        raise UpstreamFormat(problems=["тело: пустое"])
    return text


def parse[M: BaseModel](model: type[M], response: DiaryResponse) -> M:
    """Тело ответа -> модель. Пустое тело, не JSON или другая форма —
    UpstreamFormat, в нём только пути полей без значений."""
    try:
        return model.model_validate_json(_text(response))
    except ValidationError as error:
        # from None: в контексте ValidationError лежат значения полей.
        raise UpstreamFormat.from_validation(error) from None


def parse_list[M: BaseModel](model: type[M], response: DiaryResponse) -> list[M]:
    """Как parse, но тело — JSON-список (null вместо списка — тоже ошибка формата)."""
    try:
        return _list_adapter(model).validate_json(_text(response))
    except ValidationError as error:
        raise UpstreamFormat.from_validation(error) from None
