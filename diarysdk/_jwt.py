"""Разбор payload JWT дневника без проверки подписи.

Подпись проверяет сам дневник. Нам из токена нужен только срок (exp), чтобы
просроченный токен сразу получал 401, не тратя запрос к порталу.
"""

import base64
import binascii
import json
from datetime import UTC, datetime


class InvalidToken(Exception):
    """Строка не похожа на JWT дневника."""


def decode_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise InvalidToken("в JWT должно быть три части")
    body = parts[1]
    try:
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        payload = json.loads(raw)
    except (binascii.Error, ValueError) as error:
        raise InvalidToken("payload JWT не разобрался") from error
    if not isinstance(payload, dict):
        raise InvalidToken("payload JWT — не объект")
    return payload


def expires_at(token: str) -> datetime:
    exp = decode_payload(token).get("exp")
    if isinstance(exp, bool) or not isinstance(exp, int | float):
        raise InvalidToken("в JWT нет числового exp")
    try:
        return datetime.fromtimestamp(exp, tz=UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise InvalidToken("exp вне допустимого диапазона") from error
