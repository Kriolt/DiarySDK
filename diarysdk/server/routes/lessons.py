from typing import Annotated

from fastapi import APIRouter, Path

from diarysdk.models.lessons import Lesson
from diarysdk.server.routes.deps import StudentDep

router = APIRouter(tags=["расписание"])

LessonId = Annotated[int, Path(gt=0, description="id урока из расписания")]


@router.get("/lessons/{lesson_id}", summary="Урок: тема, учитель, оценки, ДЗ, материалы")
async def get_lesson(lesson_id: LessonId, student: StudentDep) -> Lesson:
    return await student.lesson(lesson_id)
