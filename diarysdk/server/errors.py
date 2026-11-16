"""Ошибка самого сервера, которой нет в `diarysdk.errors` (например, `token_missing`).

Остальное — классы из `diarysdk.errors`; в HTTP их переводит край (edge/errors.py).
"""

from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}
        self.extra = extra or {}
