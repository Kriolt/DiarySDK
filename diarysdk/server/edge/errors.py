"""Единый формат ошибок: {"error": "<код>", "message": "<по-русски>"}."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from diarysdk.errors import DiaryError, UpstreamFormat, retry_after_header, to_response
from diarysdk.server.errors import ApiError

log = logging.getLogger("diarysdk.server.edge")

# Ошибки маршрутизации самого Starlette (нет пути, не тот метод).
_ROUTING = {
    404: ("not_found", "Такого адреса нет"),
    405: ("method_not_allowed", "Этот метод здесь не поддерживается"),
}


def error_response(
    status: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": code, "message": message, **(extra or {})},
        headers=headers,
    )


async def _api_error(request: Request, error: ApiError) -> JSONResponse:
    return error_response(
        error.status, error.code, error.message, headers=error.headers, extra=error.extra
    )


async def _diary_error(request: Request, error: DiaryError) -> JSONResponse:
    # 401 — всегда про токен пользователя, 403 — про ключ потребителя, 5xx — про
    # дневник: потребитель по коду понимает, кого звать.
    status, body = to_response(error)
    if isinstance(error, UpstreamFormat):
        # Сигнал нам чинить маппинг: пути полей и типы ошибок, без значений.
        log.warning("ответ дневника не разобрался", extra={"problems": error.problems})
    wait = retry_after_header(error)
    return JSONResponse(
        status_code=status, content=body, headers={"Retry-After": wait} if wait else None
    )


async def _validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    # Значение параметра в ответ не отдаём: только какой параметр не так.
    names = sorted({str(item["loc"][-1]) for item in error.errors() if item.get("loc")})
    detail = f": {', '.join(names)}" if names else ""
    return error_response(400, "bad_request", f"Неверные параметры запроса{detail}")


async def _http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
    code, message = _ROUTING.get(error.status_code, ("bad_request", "Неверный запрос"))
    return error_response(error.status_code, code, message, headers=error.headers)


async def _unhandled(request: Request, error: Exception) -> JSONResponse:
    # Текст исключения не пишем ни в ответ, ни в журнал: в исключениях
    # HTTP-клиента лежат URL с ID ученика, а в ошибках pydantic — значения полей.
    log.error("необработанная ошибка", extra={"error_type": type(error).__name__})
    # Этот ответ отправляет ServerErrorMiddleware снаружи нашего журнала
    # запросов, поэтому no-store ставим здесь.
    return error_response(
        500,
        "internal_error",
        "Внутренняя ошибка сервиса",
        headers={"Cache-Control": "no-store"},
    )


def install(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(DiaryError, _diary_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled)
