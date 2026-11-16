"""Тела ошибок для OpenAPI: так их видит потребитель, а не FastAPI по умолчанию.

Сами ответы строит edge/errors.py; эти модели только описывают их форму в
схеме и в рантайме не участвуют.
"""

from pydantic import BaseModel, Field

from diarysdk.models.auth import LoginStep


class ErrorResponse(BaseModel):
    """Единый формат ошибки; по `error` потребитель решает, кого звать."""

    error: str = Field(description="Код ошибки: bad_request, token_expired, rate_limited…")
    message: str = Field(description="Объяснение по-русски; значений параметров в нём нет")


class LoginStepErrorResponse(ErrorResponse):
    """401 bad_code или bad_captcha: поток жив, следующий шаг — в `step`."""

    step: LoginStep | None = Field(
        default=None, description="Новый шаг входа: оставшиеся попытки или свежая капча"
    )


class UpstreamErrorResponse(ErrorResponse):
    """502 и 504: дневник не ответил или ответил ошибкой."""

    upstream_status: int | None = Field(
        default=None,
        description="Статус ответа дневника, если он был (у 502 upstream_error)",
    )
    uncertain: bool | None = Field(
        default=None,
        description=(
            "true: запись ушла, а применил ли её дневник, неизвестно (только запись). "
            "Нет поля: запись точно не прошла"
        ),
    )
