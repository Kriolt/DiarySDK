"""Общая часть запросов к дневнику: заголовки и отправка через транспорт."""

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from diarysdk._hosts import Hosts
from diarysdk._transport import DiaryResponse


def param(value: Any) -> str:
    """Значение параметра запроса: дневник ждёт true/false и даты ISO."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


class Api:
    """Чтение из дневника с токеном ученика. Заголовки — как у приложения."""

    def __init__(self, transport, hosts: Hosts, token: str) -> None:
        self._transport = transport
        self._hosts = hosts
        self._token = token

    def _headers(self, extra: Mapping[str, Any]) -> dict[str, str]:
        token = self._token
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Authorization": f"Bearer {token}",
            "Auth-Token": token,
            "Cookie": f"aupdtoken={token}; aupd_token={token}",
        }
        # Заголовок без значения (например, Profile-Id у веб-профиля) не шлём.
        headers.update({name: str(value) for name, value in extra.items() if value is not None})
        return headers

    async def _get(
        self,
        base: str,
        path: str,
        *,
        call: str,
        headers: Mapping[str, Any],
        params: Mapping[str, Any] | None = None,
    ) -> DiaryResponse:
        return await self._transport.send(
            "GET",
            base + path,
            headers=self._headers(headers),
            params={name: param(value) for name, value in (params or {}).items()},
            call=call,
        )
