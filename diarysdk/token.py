"""Токен ученика: сам JWT и срок, вычисленный локально."""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta
from typing import Literal

from diarysdk import _jwt
from diarysdk.errors import TokenExpired, TokenInvalid

# id роли в начале группы `rls`: «{2:[…]}» → «2».
_RLS_ROLE = re.compile(r"\{(\d+):")


def _expires_at(jwt: str) -> datetime | None:
    # Подпись не проверяем: её проверяет дневник, нам нужен только срок.
    # Не JWT, мусор в payload или нет exp — срока нет, и это не ошибка при
    # создании Token; но ensure_usable такой токен отвергнет.
    try:
        return _jwt.expires_at(jwt)
    except _jwt.InvalidToken:
        return None


class Token:
    __slots__ = ("expires_at", "method", "value")

    def __init__(
        self,
        value: str,
        expires_at: datetime | None = None,
        method: Literal["jwt", "password", "esia"] = "jwt",
    ) -> None:
        self.value = value
        # Как получен: из голой строки — jwt, после входа — password или esia.
        self.method = method
        if expires_at is None:
            expires_at = _expires_at(value)
        elif expires_at.tzinfo is None:
            # Срок без часового пояса считаем UTC: иначе expires_in() падал бы
            # на вычитании «наивного» и «осведомлённого» времени.
            expires_at = expires_at.replace(tzinfo=UTC)
        # None — срок неизвестен (не JWT или в нём нет exp).
        self.expires_at: datetime | None = expires_at

    def expires_in(self, now: datetime | None = None) -> timedelta | None:
        """Сколько осталось до истечения токена.

        Parameters
        ----------
        now : datetime.datetime, optional
            Момент отсчёта (с часовым поясом); по умолчанию — сейчас.

        Returns
        -------
        datetime.timedelta или None
            Отрицательное, если токен уже истёк; `None`, если срок неизвестен.
        """
        if self.expires_at is None:
            return None
        return self.expires_at - (now or datetime.now(UTC))

    def ensure_usable(self, now: datetime | None = None) -> None:
        """Токен годится для запроса: у него есть срок и он не истёк.

        Нет срока — это не токен дневника (TokenInvalid); срок вышел — TokenExpired.
        Дневник при этом не спрашивается.
        """
        left = self.expires_in(now)
        if left is None:
            raise TokenInvalid("Это не токен дневника")
        if left <= timedelta(0):
            raise TokenExpired()

    @property
    def subject_id(self) -> str | None:
        """Субъект токена (sub) из payload; нет или не разобрался — None."""
        subject = self._payload().get("sub")
        # bool — подкласс int: True стал бы субъектом «True».
        if isinstance(subject, str | int) and not isinstance(subject, bool):
            return str(subject)
        return None

    @property
    def roles(self) -> list[str]:
        """id ролей дневника из payload: 1 — ученик, 2 — родитель.

        Дневник кладёт их в `rls` строкой вида `{2:[21:2:[],…]},{222:[…]}`:
        id роли — число в начале каждой группы, пары внутри не разбираются.
        Без `rls` — `rol` строкой через запятую или списком, или `roles` списком."""
        payload = self._payload()
        rls = payload.get("rls")
        if isinstance(rls, str):
            return list(dict.fromkeys(_RLS_ROLE.findall(rls)))
        raw = payload.get("rol", payload.get("roles"))
        if isinstance(raw, str):
            return [part.strip() for part in raw.split(",") if part.strip()]
        if isinstance(raw, list):
            return [str(item) for item in raw if isinstance(item, str | int)]
        return []

    def _payload(self) -> dict:
        try:
            return _jwt.decode_payload(self.value)
        except _jwt.InvalidToken:
            return {}

    def is_expiring(self, within: timedelta = timedelta(minutes=5)) -> bool:
        """Остаётся не больше within (или уже истёк). Срок неизвестен — False."""
        left = self.expires_in()
        return left is not None and left <= within

    def __str__(self) -> str:
        # str() намеренно не отдаёт значение: токен случайно попадёт в f-строку
        # или журнал. Значение — только явно, через .value.
        return repr(self)

    def __repr__(self) -> str:
        # Первые 6 символов хеша: по ним видно «тот же токен или новый»,
        # а сам токен не восстановить.
        tag = hashlib.sha256(self.value.encode()).hexdigest()[:6]
        expires = self.expires_at.isoformat() if self.expires_at else None
        return f"Token(method={self.method}, expires_at={expires}, sha256={tag})"

    def __eq__(self, other: object) -> bool:
        # Сравнение за постоянное время: значение — секрет.
        return isinstance(other, Token) and hmac.compare_digest(
            self.value.encode(), other.value.encode()
        )

    def __hash__(self) -> int:
        return hash(self.value)
