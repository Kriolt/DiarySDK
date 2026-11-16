"""Аватар ученика: байты картинки и её тип."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Avatar:
    content: bytes = field(repr=False)
    content_type: str
