"""Параметры запросов: даты периода с описанием значений по умолчанию."""

from datetime import date
from typing import Annotated

from fastapi import Query


def period_bound(name: str, default: str):
    return Annotated[date | None, Query(alias=name, description=f"по умолчанию — {default}")]


OnDate = period_bound("date", "сегодня")
