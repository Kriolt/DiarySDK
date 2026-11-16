from fastapi import APIRouter

from diarysdk.models.school import School
from diarysdk.server.routes.deps import StudentDep

router = APIRouter(tags=["ученик"])


@router.get("/school", summary="Школа: директор, адрес, учителя, корпуса")
async def get_school(student: StudentDep) -> School:
    return await student.school()
