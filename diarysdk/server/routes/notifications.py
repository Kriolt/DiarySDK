from fastapi import APIRouter

from diarysdk.models.notifications import Notification
from diarysdk.server.routes.deps import StudentDep

router = APIRouter(tags=["лента"])


@router.get("/notifications", summary="Лента дневника: что поменялось в оценках и ДЗ")
async def get_notifications(student: StudentDep) -> list[Notification]:
    return await student.notifications()
