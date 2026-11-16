"""Проверка ключа потребителя и токена пользователя.

403 — всегда про ключ потребителя, 401 — всегда про токен пользователя:
потребитель по коду понимает, кого звать.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.routing import APIRoute
from fastapi.security import APIKeyHeader, HTTPBearer

from diarysdk.errors import BadApiKey, ForbiddenScope, TokenInvalid
from diarysdk.server.errors import ApiError
from diarysdk.server.keys import hash_key
from diarysdk.token import Token

# Схемы нужны для /docs: там видно, что эндпоинты ждут X-Api-Key и Bearer.
_api_key = APIKeyHeader(name="X-Api-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False, description="JWT дневника «Моя школа»")


async def require_consumer(request: Request, key: Annotated[str | None, Depends(_api_key)]) -> str:
    consumer = request.app.state.keys.consumer_for(key or "")
    if consumer is None:
        raise BadApiKey()
    request.state.consumer = consumer.name
    # Разрешения строки ключа, который подошёл, — не всего потребителя.
    request.state.scopes = consumer.scopes
    return consumer.name


class KeyFirstRoute(APIRoute):
    """Маршрут, у которого ключ проверяется раньше разбора тела.

    FastAPI читает и разбирает JSON до зависимостей, поэтому запрос без ключа
    и с битым телом получал бы 400, а не 403. Проверка ключа здесь не заменяет
    зависимость require_consumer, а идёт перед ней: повторный поиск ключа — это
    хеш и словарь, цены у него нет.
    """

    def get_route_handler(self) -> Callable[[Request], Awaitable[Any]]:
        inner = super().get_route_handler()

        async def handler(request: Request) -> Any:
            await require_consumer(request, request.headers.get("X-Api-Key"))
            return await inner(request)

        return handler


def require_scope(scope: str) -> Callable[..., Awaitable[None]]:
    """Зависимость: пускает только ключи с этим разрешением, иначе 403."""

    async def check(request: Request, _: Annotated[str, Depends(require_consumer)]) -> None:
        if scope not in request.state.scopes:
            raise ForbiddenScope()

    return check


async def require_token(request: Request, _: Annotated[object, Depends(_bearer)]) -> str:
    header = request.headers.get("Authorization")
    if not header:
        raise ApiError(401, "token_missing", "Нужен заголовок Authorization: Bearer <токен>")
    scheme, _, token = header.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise TokenInvalid("Токен передаётся как Authorization: Bearer <токен>")
    # Метка для журнала: по ней видно запросы одного пользователя, но сам
    # токен из неё не восстановить.
    request.state.token_tag = hash_key(token)[:12]
    # Без срока это не токен дневника, с истёкшим дневник спрашивать незачем.
    Token(token).ensure_usable(datetime.now(UTC))
    return token
