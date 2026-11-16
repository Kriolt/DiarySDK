from fastapi import APIRouter

from diarysdk.models.exams import Exam
from diarysdk.server.routes.deps import StudentDep

router = APIRouter(tags=["оценки"])


@router.get("/exams", summary="ГИА: ОГЭ, ЕГЭ и пробные (форма уточняется по живому ответу)")
async def get_exams(student: StudentDep) -> list[Exam]:
    return await student.exams()
