from fastapi import APIRouter

from diarysdk.models.periods import PeriodDay
from diarysdk.server.routes.deps import StudentDep
from diarysdk.server.routes.params import period_bound

router = APIRouter(tags=["лента"])

From = period_bound("from", "1 сентября учебного года")
To = period_bound("to", "31 августа учебного года")


@router.get("/periods", summary="Расписание периодов: каникулы и праздники")
async def get_periods(student: StudentDep, start: From = None, end: To = None) -> list[PeriodDay]:
    return await student.periods(start, end)
