"""Синхронный клиент сервиса: без async и циклов событий.

Запуск против настоящего сервиса:

    DIARYSDK_URL=https://diarysdk.example DIARYSDK_KEY=<ключ> \
    DIARY_TOKEN=<токен ученика> python sync_remote.py

Вызовы блокируют текущий поток. Внутри async-кода берите `diarysdk.remote.RemoteDiary`.
"""

import os
import sys

from diarysdk import NetworkError, TokenExpired, WriteUncertain
from diarysdk.sync import RemoteDiary


def show(api: RemoteDiary, token: str) -> None:
    student = api.student(token)
    try:
        print("Школа:", student.school().name)
        todo = [item for item in student.homework() if not item.is_done]
        if todo and todo[0].id is not None:
            try:
                student.homework_done(todo[0].id)
            except WriteUncertain:
                # Неизвестно, применилась ли отметка: перечитать, а не повторять.
                student.homework()
    except TokenExpired:
        print("Токен истёк: нужен новый")
    except NetworkError:
        print("Сервис недоступен")


def main() -> None:
    url, key, token = (os.environ.get(n) for n in ("DIARYSDK_URL", "DIARYSDK_KEY", "DIARY_TOKEN"))
    if not (url and key and token):
        sys.exit("Нужны DIARYSDK_URL, DIARYSDK_KEY и DIARY_TOKEN")
    with RemoteDiary(url, key) as api:
        show(api, token)


if __name__ == "__main__":
    main()
