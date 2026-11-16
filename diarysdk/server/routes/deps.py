"""Общие зависимости маршрутов."""

from typing import Annotated

from fastapi import Depends, Request

from diarysdk.client import Diary, Student
from diarysdk.server.edge.auth import require_consumer, require_token
from diarysdk.server.services.login import LoginService


def get_diary(request: Request) -> Diary:
    return request.app.state.diary


def get_login(request: Request) -> LoginService:
    return request.app.state.login


def get_student(
    diary: Annotated[Diary, Depends(get_diary)],
    token: Annotated[str, Depends(require_token)],
) -> Student:
    return diary.student(token)


Logins = Annotated[LoginService, Depends(get_login)]
# Ученик, чей токен пришёл в запросе: все чтения и записи идут через ядро.
StudentDep = Annotated[Student, Depends(get_student)]
Token = Annotated[str, Depends(require_token)]
# Имя потребителя по ключу: к нему привязан поток входа через ЕСИА.
Consumer = Annotated[str, Depends(require_consumer)]
