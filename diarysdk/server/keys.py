"""Ключи потребителей: файл хэшей, перечитывание по mtime, проверка.

Строка файла: `<потребитель> <sha256-хэш ключа> [разрешения]`. Разрешения —
необязательное поле через запятую (`login`, `write_profile`); они принадлежат строке, то есть
конкретному ключу, а не имени потребителя. Сам ключ сервис не хранит.

Выпуск ключа:
`python -m diarysdk.server.keys new <потребитель> [--scope ...]`.
"""

import argparse
import hashlib
import hmac
import logging
import re
import secrets
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("diarysdk.server.keys")

_HASH = re.compile(r"[0-9a-f]{64}")
_CONSUMER = re.compile(r"[A-Za-z0-9_.-]+")
_SCOPES = re.compile(r"[a-z0-9_]+(,[a-z0-9_]+)*")
# Какие разрешения умеет выдавать CLI. В файле допустимы и другие: так старый
# сервис не отвергнет файл, написанный под более новый.
KNOWN_SCOPES = ("login", "write_profile", "acknowledge_journal")


class KeyFileError(Exception):
    """Файл ключей не прочитался при старте."""


@dataclass(frozen=True)
class Consumer:
    name: str
    scopes: frozenset[str] = frozenset()


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class KeyStore:
    def __init__(
        self,
        path: Path,
        *,
        check_interval: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._path = path
        self._check_interval = check_interval
        self._clock = clock
        try:
            self._mtime = path.stat().st_mtime_ns
            self._entries = self._read()
        except OSError as error:
            raise KeyFileError(f"не прочитался файл ключей {path}") from error
        self._checked_at = clock()

    def consumer_for(self, key: str) -> Consumer | None:
        if not key:
            return None
        self._maybe_reload()
        digest = hash_key(key)
        found = None
        # Проходим все строки, не останавливаясь на первой: время ответа не
        # подсказывает, на какой строке нашёлся ключ.
        for consumer, stored in self._entries:
            if hmac.compare_digest(digest, stored):
                found = consumer
        return found

    def _maybe_reload(self) -> None:
        now = self._clock()
        if now - self._checked_at < self._check_interval:
            return
        self._checked_at = now
        try:
            mtime = self._path.stat().st_mtime_ns
            if mtime == self._mtime:
                return
            entries = self._read()
        except OSError:
            # Файл пропал или не читается: оставляем прежние ключи, чтобы
            # случайный chmod не уронил всех потребителей.
            log.warning("файл ключей не прочитался, остаются прежние ключи")
            return
        self._mtime = mtime
        self._entries = entries
        log.info("файл ключей перечитан", extra={"keys": len(entries)})

    def _read(self) -> list[tuple[Consumer, str]]:
        entries = []
        for number, line in enumerate(self._path.read_text().splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if (
                len(parts) not in (2, 3)
                or not _CONSUMER.fullmatch(parts[0])
                or not _HASH.fullmatch(parts[1])
                or (len(parts) == 3 and not _SCOPES.fullmatch(parts[2]))
            ):
                # Содержимое строки в журнал не пишем: вдруг туда вставили сам ключ.
                log.warning("строка %d файла ключей пропущена: не по формату", number)
                continue
            scopes = frozenset(parts[2].split(",")) if len(parts) == 3 else frozenset()
            entries.append((Consumer(parts[0], scopes), parts[1]))
        return entries


def _consumer_name(value: str) -> str:
    if not _CONSUMER.fullmatch(value):
        raise argparse.ArgumentTypeError("имя потребителя — латиница, цифры и _.-")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m diarysdk.server.keys")
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="выпустить ключ потребителю")
    new.add_argument("consumer", type=_consumer_name)
    new.add_argument(
        "--scope",
        choices=KNOWN_SCOPES,
        action="append",
        help=(
            "разрешение ключа, можно несколько раз: login — вход по логину и паролю "
            "через /v1/auth; write_profile — правка контактов; "
            "acknowledge_journal — отметка родителя «ознакомлен с дневником»"
        ),
    )
    args = parser.parse_args(argv)

    key = secrets.token_urlsafe(32)
    print(f"Ключ для {args.consumer} — сохраните, больше он не покажется:", file=sys.stderr)
    print(key, file=sys.stderr)
    # В stdout — только строка для файла ключей, чтобы её можно было
    # дописать перенаправлением.
    line = f"{args.consumer} {hash_key(key)}"
    if args.scope:
        # dict.fromkeys — без повторов, в порядке указания.
        line += " " + ",".join(dict.fromkeys(args.scope))
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
