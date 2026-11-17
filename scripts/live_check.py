"""Живая проверка чтений `Student` на настоящем дневнике (для мейнтейнеров).

    python scripts/live_check.py --password | --esia | --token

Секреты — только из переменных окружения DIARYSDK_LOGIN, DIARYSDK_PASSWORD,
DIARYSDK_TOKEN или из getpass; в аргументах командной строки их нет. Код
MFA и ответ на капчу-вопрос вводятся при входе через ЕСИА. Скрипт ничего
не пишет на диск и не вызывает записи (homework_done, homework_undone,
update_settings, update_contact).

Вывод — по строке на метод: `ok <метод>`, `fail <метод>: <класс ошибки>
<problems>` (problems — только пути полей и типы ошибок) или
`skip <метод>: ...`, если для аргумента нет подходящих данных. Значений
полей ответов скрипт не печатает. Код выхода 1, если был `fail`.
"""

import argparse
import asyncio
import getpass
import os
import sys
from collections.abc import Awaitable, Callable, Mapping
from typing import TextIO

from diarysdk import Captcha, Diary, LoginFlow, LoginMfa, Student, Token
from diarysdk.errors import UpstreamFormat

# Методы Student, которые меняют данные ученика: скрипт их не вызывает.
WRITES = frozenset({"homework_done", "homework_undone", "update_settings", "update_contact"})

Ask = Callable[[str], str]


def _first_id(items: list | None, pick: Callable[[object], int | None]) -> int | str:
    """Первый id из списка или причина, почему его нет (без значений полей)."""
    if items is None:
        return "чтение не удалось"
    if not items:
        return "список пуст"
    found = next((i for i in map(pick, items) if i is not None), None)
    return "ни у одного элемента нет id" if found is None else found


def describe(error: Exception) -> str:
    """Класс ошибки и, для формата ответа, пути полей; без текста сообщения."""
    problems = error.problems if isinstance(error, UpstreamFormat) else []
    return " ".join([type(error).__name__, *problems])


async def check_reads(student: Student, out: TextIO) -> bool:
    """Вызвать каждое чтение Student; True, если ни одно не упало."""
    ids: dict[str, int | str] = {}
    failed = False

    async def run(name: str, call: Callable[[], Awaitable[object]]) -> object | None:
        nonlocal failed
        try:
            result = await call()
        except Exception as error:  # любой сбой чтения — fail, а не падение скрипта
            failed = True
            print(f"fail {name}: {describe(error)}", file=out)
            return None
        print(f"ok {name}", file=out)
        return result

    async def run_with_id(name: str, key: str, call: Callable[[int], Awaitable[object]]) -> None:
        value = ids.get(key)
        if not isinstance(value, int):
            print(f"skip {name}: нет данных для аргумента ({value})", file=out)
        else:
            await run(name, lambda: call(value))

    for name, call in (
        ("me", student.me),
        ("avatar", student.avatar),
        ("school", student.school),
        ("identity", student.identity),
        ("settings", student.settings),
        ("notifications", student.notifications),
        ("exams", student.exams),
        ("curriculum", student.curriculum),
        ("periods", student.periods),
        ("final_marks", student.final_marks),
        ("rating", student.rating),
        ("rating_subjects", student.rating_subjects),
        ("rating_history", student.rating_history),
        ("homework", student.homework),
    ):
        await run(name, call)

    marks = await run("marks", student.marks)
    ids["mark"] = _first_id(marks, lambda m: m.id)
    schedule = await run("schedule", student.schedule)
    ids["lesson"] = _first_id(schedule, lambda i: i.id)
    subjects = await run("subjects", student.subjects)
    ids["subject"] = _first_id(subjects, lambda s: s.subject.id)

    await run_with_id("mark", "mark", student.mark)
    await run_with_id("lesson", "lesson", student.lesson)
    await run_with_id("subject", "subject", student.subject)
    return not failed


async def esia_login(diary: Diary, login: str, password: str, ask: Ask, ask_secret: Ask) -> Token:
    """Вход через ЕСИА: код MFA и ответ на капчу-вопрос — с клавиатуры."""
    result = await diary.login.esia(login, password)
    while isinstance(result, LoginFlow):
        if isinstance(result.mfa, LoginMfa):
            result = await result.submit_code(ask_secret("Код подтверждения: "))
        elif isinstance(result.captcha, Captcha) and result.captcha.question:
            result = await result.answer_captcha(ask_secret(f"{result.captcha.question} "))
        else:
            await result.close()
            raise SystemExit("Капча-картинка: войдите по паролю или передайте токен")
    return result


async def acquire_token(
    diary: Diary, method: str, env: Mapping[str, str], ask: Ask, ask_secret: Ask
) -> Token | str:
    if method == "token":
        return env.get("DIARYSDK_TOKEN") or ask_secret("Токен: ")
    login = env.get("DIARYSDK_LOGIN") or ask("Логин: ")
    password = env.get("DIARYSDK_PASSWORD") or ask_secret("Пароль: ")
    if method == "password":
        return await diary.login.password(login, password)
    return await esia_login(diary, login, password, ask, ask_secret)


async def run(
    method: str,
    env: Mapping[str, str],
    ask: Ask,
    ask_secret: Ask,
    out: TextIO,
    diary: Diary | None = None,
) -> int:
    async with diary or Diary() as opened:
        try:
            token = await acquire_token(opened, method, env, ask, ask_secret)
        except Exception as error:
            print(f"fail вход: {describe(error)}", file=out)
            return 1
        return 0 if await check_reads(opened.student(token), out) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Живая проверка чтений Student.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--password", dest="method", action="store_const", const="password")
    group.add_argument("--esia", dest="method", action="store_const", const="esia")
    group.add_argument("--token", dest="method", action="store_const", const="token")
    args = parser.parse_args(argv)
    return asyncio.run(run(args.method, os.environ, input, getpass.getpass, sys.stdout))


if __name__ == "__main__":
    sys.exit(main())
