from fastapi import APIRouter

from diarysdk.models.schedule import ScheduleItem
from diarysdk.server.routes.deps import StudentDep
from diarysdk.server.routes.params import period_bound

router = APIRouter(tags=["расписание"])

From = period_bound("from", "понедельник текущей недели")
To = period_bound("to", "воскресенье той же недели; период не длиннее 31 дня")


@router.get("/schedule", summary="Уроки и события с оценками и ДЗ")
async def get_schedule(
    student: StudentDep, start: From = None, end: To = None
) -> list[ScheduleItem]:
    return await student.schedule(start, end)
