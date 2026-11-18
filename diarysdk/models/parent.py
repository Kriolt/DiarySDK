"""Родитель: его профиль и ученики, к которым у него есть доступ."""

from datetime import date, datetime

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


class JournalAck(Schema):
    """Отметка родителя «ознакомлен с дневником» за неделю."""

    week: date
    # Когда отметили (по Москве); дневник не прислал — null.
    created_at: datetime | None = None
    child_id: int
