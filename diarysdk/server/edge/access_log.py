"""Журнал входящих запросов и Cache-Control: no-store для /v1/*.

Чистая ASGI-middleware, а не BaseHTTPMiddleware: счётчик запросов к
дневнику живёт в contextvar, и он должен быть виден коду маршрута.
"""

import logging
import time
from urllib.parse import parse_qsl

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from diarysdk import _metrics

log = logging.getLogger("diarysdk.access")

# Значения этих параметров — даты и ID предмета, их можно писать. Остальное скрывается:
# потребитель по ошибке мог положить в адрес что угодно, вплоть до токена.
_LOGGED_PARAMS = {"from", "to", "date", "subject"}


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        counter = [0]
        reset = _metrics.diary_calls.set(counter)
        state = scope.setdefault("state", {})
        is_v1 = scope["path"] == "/v1" or scope["path"].startswith("/v1/")
        status = 500

        async def send_and_watch(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                if is_v1:
                    MutableHeaders(scope=message)["Cache-Control"] = "no-store"
            await send(message)

        try:
            await self.app(scope, receive, send_and_watch)
        finally:
            _metrics.diary_calls.reset(reset)
            log.info(
                "request",
                extra={
                    "consumer": state.get("consumer"),
                    "method": scope["method"],
                    # Путь пишем, только если он совпал с нашим маршрутом: в
                    # наших путях только ID уроков и ДЗ, а в чужом может быть что угодно.
                    "path": _path(scope) if "route" in scope else None,
                    "params": _params(scope.get("query_string", b"")),
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "diary_calls": counter[0],
                    "token": state.get("token_tag"),
                },
            )


def _path(scope: Scope) -> str:
    # flow_id начатого входа через ЕСИА — ручка потока: её не пишем.
    path = scope["path"]
    flow_id = scope.get("path_params", {}).get("flow_id")
    if isinstance(flow_id, str) and flow_id:
        path = "/".join("***" if part == flow_id else part for part in path.split("/"))
    return path


def _params(query: bytes) -> dict[str, str]:
    pairs = parse_qsl(query.decode("latin-1"), keep_blank_values=True)
    return {name: value if name in _LOGGED_PARAMS else "***" for name, value in pairs}
