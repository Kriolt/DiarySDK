from fastapi import APIRouter

from diarysdk.models.certificates import Certificate
from diarysdk.server.routes.deps import StudentDep

router = APIRouter(tags=["ученик"])


@router.get(
    "/certificates",
    summary="Заявки на справки об обучении за два года",
    description=(
        "Только для токена родителя (child_id): ученику дневник справки не отдаёт — "
        "422 not_for_role. Форма ответа живьём не подтверждена (списки были пустыми)."
    ),
)
async def get_certificates(student: StudentDep) -> list[Certificate]:
    return await student.certificates()
