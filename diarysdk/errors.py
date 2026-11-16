"""Единая иерархия ошибок: её бросают ядро, сервер и клиент.

Код `error` из ответа сервиса отображается в класс (`from_response`), а класс
в статус и тело ответа (`to_response`); неизвестный код падает по статусу, чтобы
новый код сервера не ломал старый клиент. В исключениях нет ни паролей, ни
токенов, ни кодов входа; `str(error)` — это `message`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ValidationError

from diarysdk.models.auth import LoginStep


class DiaryError(Exception):
    """Общая база: дневник ответил ошибкой или не ответил."""

    code: ClassVar[str] = "diary_error"
    http_status: ClassVar[int] = 502
    default_message: ClassVar[str] = "Дневник ответил ошибкой, повторите позже"

    def __init__(
        self,
        message: str = "",
        *,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        text = message or self.default_message
        super().__init__(text)
        self.message = text
        # HTTP-статус ответа сервиса, если клиент его получил.
        self.status = status
        self.retry_after = retry_after
        # Код, как его прислал сервис: у класса из запасного разбора он свой.
        self.raw_code = self.code


class AuthError(DiaryError):
    """Проблема с токеном или входом пользователя: звать пользователя."""

    code = "auth_error"
    http_status = 401
    default_message = "Нужен вход: токен или вход не приняты"


class TokenInvalid(AuthError):
    code = "token_invalid"
    default_message = "Дневник не принял токен — нужен новый"


class TokenExpired(AuthError):
    code = "token_expired"
    default_message = "Срок токена истёк, нужен новый"


class BadCredentials(AuthError):
    code = "bad_credentials"
    default_message = "Неверный логин или пароль"


class _StepError(AuthError):
    """Неверный код или ответ на капчу. `step` — внутренняя нагрузка: ядро кладёт
    сюда вызов ЕСИА (MfaChallenge/CaptchaChallenge), сервис и клиент — LoginStep."""

    def __init__(
        self,
        message: str = "",
        *,
        step: object | None = None,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status=status, retry_after=retry_after)
        self.step = step
        # LoginFlow с этим шагом: его ставит клиент входа, чтобы повторить без запроса.
        self.flow: Any = None


class BadCode(_StepError):
    code = "bad_code"
    default_message = "Неверный код, попробуйте ещё раз"


class BadCaptcha(_StepError):
    code = "bad_captcha"
    default_message = "Неверный ответ на капчу — вот новая"


class FlowExpired(AuthError):
    code = "flow_expired"
    http_status = 404
    default_message = "Вход не найден или истёк — начните его заново"


class LoginBlocked(AuthError):
    code = "login_blocked"
    http_status = 409
    default_message = (
        "ЕСИА заблокировала вход или попытки кончились — попробуйте позже или вставьте JWT"
    )


class UnsupportedStep(AuthError):
    """ЕСИА просит шаг, которого сервис не умеет.

    what — название шага (уже очищенное), hint — наш совет; в ответ они уходят
    только в тексте message.
    """

    code = "unsupported_step"
    http_status = 422
    default_message = "ЕСИА просит шаг, которого сервис не умеет"

    def __init__(
        self,
        message: str = "",
        *,
        what: str = "",
        hint: str = "",
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        if not message and what:
            message = f"{self.default_message}: {what}"
            if hint:
                message = f"{message}. {hint}"
        super().__init__(message, status=status, retry_after=retry_after)
        self.what = what
        self.hint = hint


class BadRequest(DiaryError):
    code = "bad_request"
    http_status = 400
    default_message = "Неверный запрос"


class NotFound(DiaryError):
    code = "not_found"
    http_status = 404
    default_message = "В дневнике такого нет"


class NoAvatar(NotFound):
    code = "no_avatar"
    default_message = "У ученика нет аватарки"


class MultipleChildren(DiaryError):
    code = "multiple_children"
    http_status = 422
    default_message = "Токен родителя с несколькими детьми в v1 не поддерживается"


class SettingError(DiaryError):
    """Настройку записать нельзя: запись не ушла."""

    code = "setting_error"
    http_status = 409
    default_message = "Настройку в дневнике записать нельзя"


class SettingsMissing(SettingError):
    code = "settings_missing"
    default_message = "Настроек приложения в дневнике нет: записывать некуда, создать их нельзя"


class _FieldError(SettingError):
    """Ошибка про поле настройки: его имя — из нашего же запроса, не данные ученика."""

    def __init__(
        self,
        message: str = "",
        *,
        field: str = "",
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        if not message and field:
            message = f"{self.default_message}: {field}"
        super().__init__(message, status=status, retry_after=retry_after)
        self.field = field


class SettingNotSet(_FieldError):
    code = "setting_unset"
    default_message = "Настройка в дневнике не задана"


class SettingUnrestorable(_FieldError):
    code = "setting_unrestorable"
    default_message = "Текущее значение настройки сервис записать не умеет, перезапись не вернуть"


class UnsupportedContact(DiaryError):
    code = "contact_not_email"
    http_status = 422
    default_message = "Контакт не адрес почты: сервис правит только почту"


class RateLimited(DiaryError):
    code = "rate_limited"
    http_status = 429
    default_message = "Слишком много запросов, подождите"


class UpstreamError(DiaryError):
    """Дневник или сервис недоступен: повторить позже."""

    code = "upstream_error"
    http_status = 502

    def __init__(
        self,
        message: str = "",
        *,
        upstream_status: int | None = None,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status=status, retry_after=retry_after)
        # Статус, которым ответил дневник (None — до него не достучались).
        self.upstream_status = upstream_status


class UpstreamTimeout(UpstreamError):
    code = "upstream_timeout"
    http_status = 504
    default_message = "Дневник не ответил вовремя, повторите позже"


class UpstreamFormat(UpstreamError):
    """Ответ дневника не разобрался. `problems` — только пути полей и типы ошибок."""

    code = "upstream_format"
    http_status = 502
    default_message = "Ответ дневника не разобрался, повторите позже"

    def __init__(
        self,
        message: str = "",
        *,
        problems: Sequence[str] = (),
        upstream_status: int | None = None,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(
            message, upstream_status=upstream_status, status=status, retry_after=retry_after
        )
        self.problems = list(problems)

    @classmethod
    def from_validation(cls, error: ValidationError) -> Self:
        """Только путь к полю и тип ошибки: значение может быть чьим-то ФИО."""
        return cls(
            problems=[
                f"{'.'.join(str(part) for part in item['loc']) or 'тело'}: {item['type']}"
                for item in error.errors(
                    include_url=False, include_input=False, include_context=False
                )
            ]
        )


class WriteUncertain(DiaryError):
    """Запись ушла, но ответа не получили: неизвестно, применил ли её дневник.

    Автоматически не повторяется — потребитель перечитывает состояние и решает
    сам. Код и HTTP-статус — по `cause`.
    """

    code = "write_uncertain"
    default_message = "Неизвестно, применилась ли запись: перечитайте состояние"

    def __init__(
        self,
        message: str = "",
        *,
        cause: DiaryError,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status=status, retry_after=retry_after)
        self.cause = cause
        self.code = self.raw_code = cause.code
        self.http_status = cause.http_status

    @property
    def upstream_status(self) -> int | None:
        """Статус дневника, если он известен: 401/403 — запись точно не прошла."""
        return self.cause.upstream_status if isinstance(self.cause, UpstreamError) else None


class RemoteError(DiaryError):
    """Ошибка клиента: сервис не достигнут или ответил не по контракту."""

    code = "remote_error"
    default_message = "Сервис не ответил как ожидалось"


class BadApiKey(RemoteError):
    code = "bad_api_key"
    http_status = 403
    default_message = "Неверный или отсутствующий X-Api-Key"


class ForbiddenScope(RemoteError):
    code = "forbidden_scope"
    http_status = 403
    default_message = "Этому ключу не разрешена эта операция"


class NetworkError(RemoteError):
    """До сервиса не дошли или не дождались ответа."""

    code = "network_error"
    default_message = "Не удалось связаться с сервисом"


def _walk(base: type[DiaryError]) -> list[type[DiaryError]]:
    result = [base]
    for sub in base.__subclasses__():
        result.extend(_walk(sub))
    return result


# Классы без собственного кода в ответе сервиса: их не разбирают по коду.
_NOT_ON_WIRE = (WriteUncertain, NetworkError)

BY_CODE: Mapping[str, type[DiaryError]] = {
    cls.code: cls
    for cls in _walk(DiaryError)
    if not cls.__name__.startswith("_") and cls not in _NOT_ON_WIRE
} | {
    # Код сервиса без класса: сервер отвечает им на запрос без Authorization
    # (server/edge/auth.py), клиент разбирает его как TokenInvalid.
    "token_missing": TokenInvalid,
}

# Когда код неизвестен (ответ прокси или новый код сервера), смысл несёт статус:
# 401 — вход или токен, 403 — ключ потребителя, 404 — нет такого, 429 — лимит.
_BY_STATUS: Mapping[int, type[DiaryError]] = {
    401: AuthError,
    403: RemoteError,
    404: NotFound,
    429: RateLimited,
}


def parse_retry_after(value: str | None) -> float | None:
    # Сервис шлёт целые секунды; дату HTTP не разбираем — это чужой прокси.
    try:
        seconds = float(value) if value is not None else None
    except ValueError:
        return None
    return seconds if seconds is not None and math.isfinite(seconds) and seconds >= 0 else None


def retry_after_header(error: DiaryError) -> str | None:
    """Значение заголовка Retry-After (целые секунды) или None."""
    if error.retry_after is None:
        return None
    return str(max(1, math.ceil(error.retry_after)))


def to_response(error: DiaryError) -> tuple[int, dict[str, Any]]:
    """Статус и тело `{"error","message", ...}` для ответа сервера."""
    if isinstance(error, WriteUncertain):
        # Исход записи неизвестен: статус и код — причины, плюс явная метка для клиента.
        status, body = to_response(error.cause)
        return status, {**body, "uncertain": True}
    body: dict[str, Any] = {"error": error.code, "message": str(error)}
    if type(error) is UpstreamError:
        body["upstream_status"] = error.upstream_status
    if isinstance(error, _StepError) and isinstance(error.step, BaseModel):
        body["step"] = error.step.model_dump(mode="json")
    return error.http_status, body


def from_response(status: int, body: Any, retry_after: str | None = None) -> DiaryError:
    """Разбирает `{"error","message"}`; тело не по форме (прокси) не роняет разбор."""
    data = body if isinstance(body, dict) else {}
    code = data.get("error")
    message = data.get("message") if isinstance(data.get("message"), str) else f"HTTP {status}"
    cls = BY_CODE.get(code) if isinstance(code, str) else None
    cls = cls or _BY_STATUS.get(status)
    if cls is None:
        cls = UpstreamError if status >= 500 else DiaryError
    kwargs: dict[str, Any] = {"status": status, "retry_after": parse_retry_after(retry_after)}
    if issubclass(cls, UpstreamError):
        upstream = data.get("upstream_status")
        kwargs["upstream_status"] = upstream if isinstance(upstream, int) else None
    if issubclass(cls, _StepError):
        kwargs["step"] = _parse_step(data.get("step"))
    error = cls(message, **kwargs)
    error.raw_code = code if isinstance(code, str) else f"http_{status}"
    return error


def _parse_step(raw: Any) -> LoginStep | None:
    try:
        return LoginStep.model_validate(raw)
    except ValidationError:
        return None
