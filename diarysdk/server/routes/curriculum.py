from typing import Annotated

from fastapi import APIRouter, Path

from diarysdk.models.curriculum import ControlWork, Curriculum, ProgramModule
from diarysdk.server.routes.deps import StudentDep
from diarysdk.server.routes.params import period_bound

router = APIRouter(tags=["школа"])

GroupId = Annotated[int, Path(gt=0, description="id группы из /v1/identity (person.groups)")]
From = period_bound("from", "1 сентября")
To = period_bound("to", "31 августа; период не длиннее 366 дней")


@router.get("/curriculum", summary="Учебный план параллели; плана нет — 404")
async def get_curriculum(student: StudentDep) -> Curriculum:
    return await student.curriculum()


@router.get("/groups/{group_id}/program", summary="Рабочая программа группы: разделы, темы, уроки")
async def get_work_program(student: StudentDep, group_id: GroupId) -> list[ProgramModule]:
    return await student.work_program(group_id)


@router.get(
    "/control-works",
    summary="Контрольные работы за период",
    description="Форма ответа дневника живьём не подтверждена (ответы были пустыми).",
)
async def get_control_works(
    student: StudentDep, start: From = None, end: To = None
) -> list[ControlWork]:
    return await student.control_works(start, end)
