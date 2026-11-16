"""Пересобирает tests/openapi.json из схемы приложения.

    python scripts/openapi_snapshot.py

Запускать после любого изменения контракта; тест
tests/remote/test_release.py сравнивает файл со схемой приложения, и
ломающее изменение видно в diff PR. Ключи отсортированы, чтобы diff
показывал только настоящие правки.
"""

import json
import tempfile
from pathlib import Path

from diarysdk.server.app import create_app
from diarysdk.server.config import Settings

TARGET = Path(__file__).resolve().parents[1] / "tests" / "openapi.json"


def render() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        keys = Path(tmp) / "api-keys"
        keys.write_text("", encoding="utf-8")
        schema = create_app(Settings(keys_file=keys, version="snapshot")).openapi()
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    TARGET.write_text(render(), encoding="utf-8")
    print(f"записано {TARGET}")
