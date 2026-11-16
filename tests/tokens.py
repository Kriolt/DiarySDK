"""Подставные JWT дневника для тестов: подпись не проверяется, важен payload."""

import base64
import json
from datetime import UTC, datetime, timedelta


def _part(data) -> str:
    raw = data if isinstance(data, bytes) else json.dumps(data).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_token(exp: datetime | None = None, **claims) -> str:
    payload = dict(claims)
    if exp is not None:
        payload["exp"] = int(exp.timestamp())
    return f"{_part({'alg': 'RS256', 'typ': 'JWT'})}.{_part(payload)}.c2lnbmF0dXJl"


def valid_token(**claims) -> str:
    return make_token(datetime.now(UTC) + timedelta(hours=1), sub="1000001", **claims)
