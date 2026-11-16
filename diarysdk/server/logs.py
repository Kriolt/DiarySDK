"""Журнал: JSON-строки в stdout.

Заголовки и тела не пишутся никогда. Текст исключений тоже: в исключениях
HTTP-клиента лежат URL с ID ученика, а в ошибках pydantic — значения полей.
Пишутся только тип исключения и место в коде.
"""

import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from typing import TextIO

# color_message — копия сообщения с ANSI-цветами от uvicorn: в JSON-журнале лишняя.
_STANDARD = set(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "taskName",
    "color_message",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "time": datetime.fromtimestamp(record.created, UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD:
                data[key] = value
        if record.exc_info and record.exc_info[1] is not None:
            error = record.exc_info[1]
            data["error_type"] = type(error).__name__
            data["error_at"] = [
                f"{frame.filename}:{frame.lineno} {frame.name}"
                for frame in traceback.extract_tb(error.__traceback__)
            ]
        return json.dumps(data, ensure_ascii=False, default=str)


def configure(stream: TextIO = sys.stdout, level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Эти клиенты на INFO пишут URL запросов, а в URL дневника — ID
    # ученика и GUID.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
