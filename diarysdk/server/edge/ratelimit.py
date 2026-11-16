"""Ограничение частоты на потребителя: ведро жетонов в памяти.

Процесс один, поэтому общий счётчик не нужен. Лимит защищает дневник: баг
потребителя не должен устроить порталу нагрузку, за которую забанят IP.
"""

import time
from collections.abc import Callable

from fastapi import Request

from diarysdk.errors import RateLimited


class RateLimiter:
    def __init__(
        self, rate: float, burst: int, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._rate = rate
        self._burst = burst
        self._clock = clock
        # потребитель → (жетоны, когда пересчитаны)
        self._buckets: dict[str, tuple[float, float]] = {}

    def acquire(self, consumer: str) -> float | None:
        """None — можно; иначе сколько секунд ждать следующего жетона."""
        now = self._clock()
        tokens, updated = self._buckets.get(consumer, (float(self._burst), now))
        tokens = min(float(self._burst), tokens + (now - updated) * self._rate)
        if tokens >= 1:
            self._buckets[consumer] = (tokens - 1, now)
            return None
        self._buckets[consumer] = (tokens, now)
        return (1 - tokens) / self._rate


# Отдельный счётчик стартов входа: 5 в минуту на потребителя (спек SDK).
# Не даёт перебирать пароли через нас; общий лимит для этого слишком щедр.
LOGIN_STARTS_PER_MINUTE = 5


def login_limiter() -> RateLimiter:
    return RateLimiter(LOGIN_STARTS_PER_MINUTE / 60, LOGIN_STARTS_PER_MINUTE)


def _enforce(limiter: RateLimiter, consumer: str, message: str) -> None:
    wait = limiter.acquire(consumer)
    if wait is not None:
        raise RateLimited(message, retry_after=wait)


async def enforce_rate_limit(request: Request) -> None:
    _enforce(request.app.state.limiter, request.state.consumer, "Слишком много запросов, подождите")


async def enforce_login_rate_limit(request: Request) -> None:
    """Старт входа: POST /v1/auth/password (и /v1/auth/esia). Шаги уже
    начатого входа этим счётчиком не считаются."""
    _enforce(
        request.app.state.login_limiter,
        request.state.consumer,
        "Слишком много попыток входа, подождите",
    )
