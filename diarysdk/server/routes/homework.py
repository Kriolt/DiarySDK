from typing import Annotated

from fastapi import APIRouter, Path, Response

from diarysdk.models.homework import Homework
from diarysdk.server.routes.deps import StudentDep
from diarysdk.server.routes.params import period_bound

router = APIRouter(tags=["расписание"])

From = period_bound("from", "сегодня (по дате сдачи)")
To = period_bound("to", "через 7 дней; период не длиннее 31 дня")
HomeworkId = Annotated[int, Path(gt=0, description="id из /v1/homework")]


@router.get("/homework", summary="Домашние задания по дате сдачи, с материалами")
async def get_homework(student: StudentDep, start: From = None, end: To = None) -> list[Homework]:
    return await student.homework(start, end)


# Запись не повторяется: после 502 и 504 неизвестно, принял ли её дневник, —
# потребитель перечитывает /v1/homework.
@router.post(
    "/homework/{homework_id}/done",
    status_code=204,
    response_class=Response,
    summary="Отметить ДЗ выполненным",
)
async def mark_homework_done(student: StudentDep, homework_id: HomeworkId) -> Response:
    await student.homework_done(homework_id)
    return Response(status_code=204)


@router.delete(
    "/homework/{homework_id}/done",
    status_code=204,
    response_class=Response,
    summary="Снять отметку о выполнении ДЗ",
)
async def unmark_homework_done(student: StudentDep, homework_id: HomeworkId) -> Response:
    await student.homework_undone(homework_id)
    return Response(status_code=204)
