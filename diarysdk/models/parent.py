"""Родитель: его профиль и ученики, к которым у него есть доступ."""

from diarysdk.models.common import Schema, SchoolBrief
from diarysdk.models.me import TokenExpiry


class ParentMe(Schema):
    """Профиль владельца токена-родителя. СНИЛС и документы — в `identity()`."""

    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    type: str | None = None
    email: str | None = None
    phone: str | None = None
    token: TokenExpiry


class Child(Schema):
    """Ученик, доступный родителю; `id` — для `parent.student(id)`."""

    id: int
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    school: SchoolBrief
    class_name: str | None = None
    is_legal_representative: bool | None = None
