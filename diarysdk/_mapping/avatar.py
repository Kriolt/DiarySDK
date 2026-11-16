"""Список аватарок avatarmanagement → ID картинки для /v1/me/avatar.

Форма — по запросу сайта: [{id, url, default}]. Берём аватарку с
default, иначе первую; url из ответа не используем — адрес картинки строим
сами, на хосте дневника.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from diarysdk.errors import UpstreamFormat


class _Avatar(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    default: bool = False


_AVATARS = TypeAdapter(list[_Avatar])


def avatar_id(data: Any) -> int | None:
    """None — аватарок нет."""
    try:
        avatars = _AVATARS.validate_python(data)
    except ValidationError as error:
        raise UpstreamFormat.from_validation(error) from None
    chosen = next((a for a in avatars if a.default), avatars[0] if avatars else None)
    return chosen.id if chosen else None
