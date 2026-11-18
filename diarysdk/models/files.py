"""Файл от дневника: байты, тип и имя для сохранения."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DiaryFile:
    content: bytes = field(repr=False)
    content_type: str
    filename: str | None = None
