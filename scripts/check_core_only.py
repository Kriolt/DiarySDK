"""Проверка установки без extras: ядро, remote и sync не тянут сервер.

Запускать в чистом окружении после `pip install .` (без `[server]`):
`python scripts/check_core_only.py`.
"""

import sys

import diarysdk
import diarysdk.remote
import diarysdk.sync  # noqa: F401

FORBIDDEN = ("fastapi", "starlette", "uvicorn", "diarysdk.server")


def main() -> int:
    loaded = sorted(
        name for name in sys.modules for f in FORBIDDEN if name == f or name.startswith(f + ".")
    )
    if loaded:
        print("без extras загрузилось лишнее:", ", ".join(loaded), file=sys.stderr)
        return 1
    print("ядро, remote и sync загружаются без сервера")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
