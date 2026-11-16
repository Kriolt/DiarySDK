"""Прямой доступ к дневнику (async): токен ученика → школа, оценки, домашние задания.

Запуск (нужен адрес из России и действующий токен ученика):

    DIARY_TOKEN=<токен ученика> python direct.py

Токен — JWT из дневника; если его нет, получите его входом (см. bot_flow.py).
"""

import asyncio
import os
import sys

from diarysdk import Diary, TokenExpired, UpstreamError


async def show(api: Diary, token: str) -> None:
    student = api.student(token)
    try:
        school = await student.school()
        print("Школа:", school.name)
        for mark in (await student.marks())[:5]:
            print(mark.date, mark.subject.name if mark.subject else "?", mark.value)
        for item in await student.homework():
            print("ДЗ:", item.due, "готово" if item.is_done else "не сделано")
    except TokenExpired:
        print("Токен истёк: нужен новый")
    except UpstreamError as error:
        print("Дневник недоступен:", error.message)


async def main() -> None:
    token = os.environ.get("DIARY_TOKEN")
    if not token:
        sys.exit("Нужен DIARY_TOKEN")
    # `async with` закрывает соединения, когда работа закончена.
    async with Diary() as api:
        await show(api, token)


if __name__ == "__main__":
    asyncio.run(main())
