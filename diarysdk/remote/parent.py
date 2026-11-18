"""Родитель через сервис: тот же интерфейс, что у `diarysdk.Parent`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from diarysdk.models.identity import Identity
from diarysdk.models.parent import Child, ParentMe
from diarysdk.models.settings import Settings, SettingsUpdate
from diarysdk.remote import _core
from diarysdk.remote._core import Avatar, Request
from diarysdk.remote.student import RemoteStudent, as_token
from diarysdk.token import Token

if TYPE_CHECKING:
    from diarysdk.remote.client import RemoteDiary


class RemoteParent:
    """Родитель через сервис; создаётся `diary.parent(token)` без запросов."""

    def __init__(self, diary: RemoteDiary, token: str | Token) -> None:
        self._diary = diary
        self._token = as_token(token)
        # Ошибки токена и хук on_token_expired — как у ученика.
        self._self = RemoteStudent(diary, self._token)

    @property
    def token(self) -> Token:
        return self._token

    def __repr__(self) -> str:
        return f"RemoteParent(token={self._token!r})"

    async def _call(self, spec: Request) -> Any:
        return await self._self._call(spec)

    def student(self, child_id: int) -> RemoteStudent:
        return RemoteStudent(self._diary, self._token, child_id)

    async def me(self) -> ParentMe:
        return await self._call(_core.parent_me())

    async def identity(self) -> Identity:
        return await self._call(_core.parent_identity())

    async def avatar(self) -> Avatar:
        return await self._call(_core.parent_avatar())

    async def children(self) -> list[Child]:
        return await self._call(_core.parent_children())

    async def settings(self) -> Settings:
        return await self._call(_core.parent_settings())

    async def update_settings(self, update: SettingsUpdate) -> None:
        await self._call(_core.parent_update_settings(update))

    async def update_contact(self, contact_id: int, value: str) -> None:
        await self._call(_core.parent_update_contact(contact_id, value))
