"""Общие зависимости маршрутов."""

from typing import Annotated

from fastapi import Depends, Query, Request

from diarysdk.client import Diary, Parent, Student
from diarysdk.server.edge.auth import require_consumer, require_token
from diarysdk.server.services.login import LoginService


def get_diary(request: Request) -> Diary:
    return request.app.state.diary


def get_login(request: Request) -> LoginService:
    return request.app.state.login


ChildId = Annotated[
    int | None,
    Query(
        gt=0,
        description=(
            "id ученика из /v1/parent/children — для токена родителя; "
            "без него — единственный ученик токена"
        ),
    ),
]


def get_student(
    diary: Annotated[Diary, Depends(get_diary)],
    token: Annotated[str, Depends(require_token)],
    child_id: ChildId = None,
) -> Student:
    if child_id is None:
        return diary.student(token)
    return diary.parent(token).student(child_id)


def get_parent(
    diary: Annotated[Diary, Depends(get_diary)],
    token: Annotated[str, Depends(require_token)],
) -> Parent:
    return diary.parent(token)


Logins = Annotated[LoginService, Depends(get_login)]
# Ученик, чей токен пришёл в запросе: все чтения и записи идут через ядро.
StudentDep = Annotated[Student, Depends(get_student)]
# Родитель — владелец токена из запроса.
ParentDep = Annotated[Parent, Depends(get_parent)]
Token = Annotated[str, Depends(require_token)]
# Имя потребителя по ключу: к нему привязан поток входа через ЕСИА.
Consumer = Annotated[str, Depends(require_consumer)]
