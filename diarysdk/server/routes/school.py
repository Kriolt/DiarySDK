from typing import Annotated

from fastapi import APIRouter, Query

from diarysdk.models.school import School, SchoolTeacher
from diarysdk.server.routes.deps import StudentDep

router = APIRouter(tags=["ученик"])


@router.get("/school", summary="Школа: директор, адрес, учителя, корпуса")
async def get_school(student: StudentDep) -> School:
    return await student.school()


@router.get("/school/teachers", summary="Учителя школы: имя, роли, предметы")
async def get_school_teachers(
    student: StudentDep,
    name: Annotated[
        str | None, Query(min_length=1, max_length=100, description="часть имени")
    ] = None,
) -> list[SchoolTeacher]:
    return await student.school_teachers(name)
