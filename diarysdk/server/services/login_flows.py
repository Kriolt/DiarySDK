"""Потоки входа через ЕСИА между запросами потребителя — в памяти процесса.

Реестр хранит `LoginFlow` ядра под flow_id и потребителем. Срок потока, проверка
шага и закрытие после сбоя — в самом `LoginFlow`; здесь только то, чего ядро не
знает: чей поток, лимиты и очередь шагов по HTTP.

Живёт поток 5 минут с последнего шага, у потребителя их не больше трёх, всего —
не больше ста. Процесс один, поэтому хватает словаря; после перезапуска потоки
пропадают, и потребитель начинает вход заново.

Решения:
- сверх лимита (3 на потребителя или 100 всего) новый старт получает
  429 rate_limited с Retry-After до истечения старшего потока, а чужие и свои
  начатые потоки не вытесняются: иначе один потребитель мог бы сбрасывать
  вход другого;
- место занимается до похода в ЕСИА (reserve), а не после: два
  одновременных старта не превысят лимит;
- шаги одного потока идут по очереди: у записи своя блокировка, второй запрос
  ждёт первого (а не получает 409 — такого кода в контракте нет) и потом видит
  поток таким, каким его оставил первый. Ждёт он не дольше LOCK_WAIT
  (см. services/login.py). Занятый поток уборка не трогает;
- истёкшие потоки убирает не только reserve/find, но и уборщик
  sweep_forever, которого app.py запускает на время жизни приложения: раз в
  SWEEP_INTERVAL (30 с).
"""

import asyncio
import logging
import math
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from diarysdk._port import FLOW_TTL
from diarysdk.client import LoginFlow
from diarysdk.errors import FlowExpired, RateLimited

FLOWS_PER_CONSUMER = 3
FLOWS_TOTAL = 100
SWEEP_INTERVAL = 30.0

log = logging.getLogger("diarysdk.login")


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(eq=False)
class Flow:
    flow_id: str
    consumer: str
    # Срок места, пока поток ещё не начат; дальше срок ведёт сам LoginFlow.
    reserved_until: datetime
    # None — место занято, а первый шаг ещё идёт.
    login: LoginFlow | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def expires_at(self) -> datetime:
        return self.login.expires_at if self.login is not None else self.reserved_until


class LoginFlows:
    def __init__(
        self,
        *,
        ttl: timedelta = FLOW_TTL,
        per_consumer: int = FLOWS_PER_CONSUMER,
        total: int = FLOWS_TOTAL,
        now: Callable[[], datetime] = _now,
    ) -> None:
        self._ttl = ttl
        self._per_consumer = per_consumer
        self._total = total
        self._now = now
        self._flows: dict[str, Flow] = {}

    def __len__(self) -> int:
        return len(self._flows)

    async def reserve(self, consumer: str) -> Flow:
        """Место под новый поток; сверх лимита — 429 rate_limited."""
        await self.sweep()
        own = [flow for flow in self._flows.values() if flow.consumer == consumer]
        if len(own) >= self._per_consumer:
            raise self._limited(
                own, "Слишком много незаконченных входов — закончите или отмените их"
            )
        if len(self._flows) >= self._total:
            raise self._limited(list(self._flows.values()), "Сервис занят входами, подождите")
        flow = Flow(
            flow_id=secrets.token_urlsafe(16),
            consumer=consumer,
            reserved_until=self._now() + self._ttl,
        )
        self._flows[flow.flow_id] = flow
        return flow

    async def activate(self, flow: Flow, login: LoginFlow) -> None:
        # Пока шёл первый шаг, поток могли выбросить (остановка сервиса):
        # вход не должен прицепиться к забытой записи и жить в памяти без
        # хозяина — закрываем его и отвечаем как на истёкший.
        if not self.is_open(flow):
            await login.close()
            raise FlowExpired()
        flow.login = login

    async def find(self, consumer: str, flow_id: str) -> Flow:
        await self.sweep()
        flow = self._flows.get(flow_id)
        if flow is None or flow.login is None or flow.consumer != consumer:
            raise FlowExpired()
        return flow

    def is_open(self, flow: Flow) -> bool:
        return self._flows.get(flow.flow_id) is flow

    async def drop(self, flow: Flow) -> None:
        """Забыть поток и закрыть вход. Повторный вызов безвреден."""
        if self._flows.get(flow.flow_id) is flow:
            del self._flows[flow.flow_id]
        if flow.login is not None:
            await flow.login.close()
            flow.login = None

    async def close_all(self) -> None:
        for flow in list(self._flows.values()):
            await self.drop(flow)

    async def sweep(self) -> None:
        """Закрыть и забыть истёкшие потоки. Занятые (шаг ещё идёт) — не трогать."""
        now = self._now()
        for flow in list(self._flows.values()):
            if flow.expires_at <= now and not flow.lock.locked():
                await self.drop(flow)

    def _limited(self, flows: list[Flow], message: str) -> RateLimited:
        soonest = min(flow.expires_at for flow in flows)
        wait = max(1, math.ceil((soonest - self._now()).total_seconds()))
        return RateLimited(message, retry_after=wait)


class _Sweepable(Protocol):
    async def sweep(self) -> None: ...


async def sweep_forever(flows: _Sweepable, *, interval: float = SWEEP_INTERVAL) -> None:
    """Уборщик: раз в interval убирает истёкшие потоки. Ошибка уборки его не
    останавливает; в журнал идёт только её тип — в тексте могут быть данные."""
    while True:
        await asyncio.sleep(interval)
        try:
            await flows.sweep()
        except Exception as error:
            log.error("уборка потоков входа упала", extra={"error_type": type(error).__name__})
