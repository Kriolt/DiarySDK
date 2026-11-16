"""Ошибки в схеме OpenAPI: описываем то, что сервис отвечает на самом деле.

FastAPI сам рекламирует `422 HTTPValidationError`, а наш обработчик
(edge/errors.py) отвечает `400 bad_request` в формате `{"error","message"}`.
Здесь схема приводится в соответствие с ответами; рантайм не трогается: это
пост-обработка уже собранной схемы, а не новые обработчики.
"""

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from diarysdk.server.schemas.errors import (
    ErrorResponse,
    LoginStepErrorResponse,
    UpstreamErrorResponse,
)

_STEP_PATHS = ("/v1/auth/esia/{flow_id}/code", "/v1/auth/esia/{flow_id}/captcha")
_LOGIN_PATHS = ("/v1/auth/password", "/v1/auth/esia")
# Эти операции не ходят в дневник: токен читают из самого JWT, отмена только закрывает поток.
_NO_DIARY = ("/v1/auth/token",)
_MODELS = (ErrorResponse, LoginStepErrorResponse, UpstreamErrorResponse)


def _ref(model: type[BaseModel]) -> dict[str, Any]:
    return {"$ref": f"#/components/schemas/{model.__name__}"}


def _response(model: type[BaseModel], description: str) -> dict[str, Any]:
    return {"description": description, "content": {"application/json": {"schema": _ref(model)}}}


def _describe(path: str, method: str, operation: dict[str, Any]) -> None:
    responses: dict[str, Any] = operation["responses"]
    validated = "422" in responses
    responses.pop("422", None)
    is_login = path.startswith("/v1/auth/") and path != "/v1/auth/token"
    cancel = method == "delete" and path == "/v1/auth/esia/{flow_id}"
    calls_diary = path not in _NO_DIARY and not cancel

    if validated:
        responses["400"] = _response(
            ErrorResponse, "bad_request: неверные параметры или тело запроса (названо поле)"
        )
    if path in _STEP_PATHS:
        responses["401"] = _response(
            LoginStepErrorResponse, "bad_code или bad_captcha: поток жив, следующий шаг в `step`"
        )
    elif path in _LOGIN_PATHS:
        responses["401"] = _response(ErrorResponse, "bad_credentials: неверный логин или пароль")
    elif not is_login:
        responses["401"] = _response(
            ErrorResponse, "token_missing, token_invalid или token_expired: нужен токен ученика"
        )
    responses["403"] = _response(
        ErrorResponse, "bad_api_key или forbidden_scope: ключ потребителя не подходит"
    )
    if "{" in path and not cancel:
        responses["404"] = _response(
            ErrorResponse,
            "flow_expired: вход не найден или истёк"
            if is_login
            else "not_found или no_avatar: такого нет",
        )
    elif path == "/v1/me/avatar":
        responses["404"] = _response(ErrorResponse, "no_avatar: у ученика нет аватарки")
    if is_login and path != "/v1/auth/esia/{flow_id}/captcha/renew":
        responses["409"] = _response(ErrorResponse, "login_blocked: ЕСИА заблокировала вход")
    if path == "/v1/settings" and method == "patch":
        responses["409"] = _response(
            ErrorResponse,
            "settings_missing, setting_unset или setting_unrestorable: записать нельзя",
        )
    if is_login and not cancel:
        responses["422"] = _response(ErrorResponse, "unsupported_step: ЕСИА просит неизвестный шаг")
    elif path.startswith("/v1/identity/contacts/"):
        responses["422"] = _response(ErrorResponse, "contact_not_email: правится только почта")
    elif calls_diary and not is_login:
        responses["422"] = _response(
            ErrorResponse, "multiple_children: токен родителя с несколькими детьми"
        )
    responses["429"] = _response(ErrorResponse, "rate_limited: заголовок Retry-After — секунды")
    if calls_diary:
        responses["502"] = _response(
            UpstreamErrorResponse, "upstream_error или upstream_format: сбой дневника"
        )
        responses["504"] = _response(UpstreamErrorResponse, "upstream_timeout: дневник не ответил")


def install(app: FastAPI) -> None:
    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = FastAPI.openapi(app)
            for path, item in schema["paths"].items():
                for method, operation in item.items():
                    _describe(path, method, operation)
            components = schema.setdefault("components", {}).setdefault("schemas", {})
            for name in ("HTTPValidationError", "ValidationError"):
                components.pop(name, None)
            for model in _MODELS:
                spec = model.model_json_schema(ref_template="#/components/schemas/{model}")
                for name, definition in spec.pop("$defs", {}).items():
                    components.setdefault(name, definition)
                components[model.__name__] = spec
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
