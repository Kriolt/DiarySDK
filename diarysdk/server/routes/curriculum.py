from fastapi import APIRouter

from diarysdk.models.curriculum import Curriculum
from diarysdk.server.routes.deps import StudentDep

router = APIRouter(tags=["школа"])


@router.get("/curriculum", summary="Учебный план параллели; плана нет — 404")
async def get_curriculum(student: StudentDep) -> Curriculum:
    return await student.curriculum()
