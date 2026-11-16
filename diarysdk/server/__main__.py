"""Запуск сервиса: python -m diarysdk.server."""

import uvicorn

from diarysdk.server import logs
from diarysdk.server.app import create_app
from diarysdk.server.config import Settings


def main() -> None:
    logs.configure()
    settings = Settings.from_env()
    # Журнал запросов пишет наш край; свой журнал uvicorn выключен, чтобы
    # строки не дублировались.
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
