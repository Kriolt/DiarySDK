"""Счётчик запросов к дневнику в рамках текущего входящего вызова.

Его ставит журнал запросов сервера (или любой другой вызывающий), увеличивает
транспорт. Без счётчика вызовы ничего не считают.
"""

from contextvars import ContextVar

diary_calls: ContextVar[list[int] | None] = ContextVar("diary_calls", default=None)


def count_diary_call() -> None:
    counter = diary_calls.get()
    if counter is not None:
        counter[0] += 1
