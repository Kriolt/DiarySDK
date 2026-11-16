"""Общие части схем ответов.

Поле, которого дневник не дал, приходит как null: все поля необязательные,
но всегда присутствуют в ответе.
"""

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )


class Subject(Schema):
    id: int | None = None
    name: str | None = None


class PersonName(Schema):
    last_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None


class SchoolBrief(Schema):
    id: int | None = None
    name: str | None = None
    short_name: str | None = None
    municipality: str | None = None


class ClassUnit(Schema):
    # id — это class_unit_id: по нему видно, что двое из одного класса.
    id: int | None = None
    name: str | None = None
    level: int | None = None


class Material(Schema):
    title: str | None = None
    url: str | None = None
    description: str | None = None
    content_type: str | None = None
    # Вид материала и действие с ним, как в дневнике («Вложения», «Посмотреть»).
    type_name: str | None = None
    action_name: str | None = None
