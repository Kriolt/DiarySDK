"""RemoteDiary: тот же интерфейс, что у `Diary`, но через сервер."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Self

import httpx

from diarysdk.errors import TokenInvalid
from diarysdk.remote import _core
from diarysdk.remote._core import Request
from diarysdk.remote.auth import RemoteLogin
from diarysdk.remote.parent import RemoteParent
from diarysdk.remote.student import RemoteStudent
from diarysdk.token import Token

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RATE_WAIT = 2.0


class _Config:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float,
        max_rate_wait: float,
        on_token_expired: Callable[[Token], Awaitable[None] | None] | None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_rate_wait = max_rate_wait
        self.on_token_expired = on_token_expired

    def headers(self, token: str | None) -> dict[str, str]:
        headers = {"X-Api-Key": self.api_key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers


class RemoteDiary:
    """Дневник через сервис: `async with RemoteDiary(url, key) as diary`."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_rate_wait: float = DEFAULT_MAX_RATE_WAIT,
        on_token_expired: Callable[[Token], Awaitable[None] | None] | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = _Config(
            base_url,
            api_key,
            timeout=timeout,
            max_rate_wait=max_rate_wait,
            on_token_expired=on_token_expired,
        )
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(follow_redirects=False)
        self.login = RemoteLogin(self)

    def __repr__(self) -> str:
        return f"RemoteDiary(base_url={self._config.base_url!r})"

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Закрыть соединения; чужой `http` остаётся хозяину."""
        if self._owns_http:
            await self._http.aclose()

    def student(self, token: str | Token) -> RemoteStudent:
        return RemoteStudent(self, token)

    def parent(self, token: str | Token) -> RemoteParent:
        return RemoteParent(self, token)

    async def _send(self, spec: Request, token: str | None = None) -> Any:
        if token is not None and not token.isascii():
            # В заголовок такое не положить; как и ядро, это «не токен дневника».
            raise TokenInvalid("Это не токен дневника")
        plan = _core.exchange(spec, self._config.max_rate_wait)
        action = next(plan)
        while True:
            outcome: Any = None
            if isinstance(action, _core.Sleep):
                await asyncio.sleep(action.seconds)
            else:
                try:
                    outcome = await self._http.request(
                        spec.method,
                        self._config.base_url + spec.path,
                        params=_core.build_params(spec.params),
                        json=spec.body,
                        headers=self._config.headers(token),
                        timeout=self._config.timeout,
                    )
                except httpx.TransportError as cause:
                    outcome = cause
            try:
                action = plan.send(outcome)
            except StopIteration as done:
                return done.value
