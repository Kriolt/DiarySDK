"""StudentContext по токену и его кэш в памяти.

Ключ — SHA-256 токена и выбранный ребёнок родителя: сам токен в кэше не
лежит. Срок 10 минут, не больше
1000 записей (LRU). Одновременные запросы с одним токеном ждут один общий
запрос профиля — иначе десяток экранов бота, открытых разом, дал бы десяток
одинаковых запросов к дневнику.
"""

import asyncio
import hashlib
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import replace

from diarysdk._port import StudentContext

# (SHA-256 токена, id выбранного ребёнка или None).
type _Key = tuple[str, int | None]


def hash_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ContextCache:
    def __init__(
        self,
        resolve: Callable[[str, int | None], Awaitable[StudentContext]],
        *,
        ttl: float = 600.0,
        maxsize: int = 1000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._resolve = resolve
        self._ttl = ttl
        self._maxsize = maxsize
        self._clock = clock
        self._entries: OrderedDict[_Key, tuple[StudentContext, float]] = OrderedDict()
        self._pending: dict[_Key, asyncio.Future[StudentContext]] = {}

    async def get(self, token: str, child_id: int | None = None) -> StudentContext:
        key = (hash_key(token), child_id)
        entry = self._entries.get(key)
        if entry is not None:
            context, expires = entry
            if expires > self._clock():
                self._entries.move_to_end(key)
                return context
            del self._entries[key]

        pending = self._pending.get(key)
        if pending is None:
            pending = asyncio.ensure_future(self._load(key, token, child_id))
            # Если все ждущие отменились, ошибку всё равно надо забрать, иначе
            # asyncio напишет в журнал «exception was never retrieved».
            pending.add_done_callback(lambda f: f.cancelled() or f.exception())
            self._pending[key] = pending
        # shield: отмена одного ждущего (клиент ушёл) не отменяет общий запрос.
        return await asyncio.shield(pending)

    def evict(self, token: str, child_id: int | None = None) -> None:
        self._entries.pop((hash_key(token), child_id), None)

    async def _load(self, key: _Key, token: str, child_id: int | None) -> StudentContext:
        try:
            context = await self._resolve(token, child_id)
        finally:
            self._pending.pop(key, None)
        # Разобранный профиль достаётся только тем, кто ждал эту загрузку; в кэше
        # он не живёт: me/identity из кэшированного контекста спрашивают свежий.
        self._entries[key] = (replace(context, profile=None), self._clock() + self._ttl)
        self._entries.move_to_end(key)
        while len(self._entries) > self._maxsize:
            self._entries.popitem(last=False)
        return context
