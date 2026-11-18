from typing import Annotated

from fastapi import APIRouter, Path

from diarysdk.models.curriculum import SubjectTopic
from diarysdk.models.subjects import SubjectDetail, SubjectSummary
from diarysdk.server.routes.deps import StudentDep

router = APIRouter(tags=["оценки"])

SubjectId = Annotated[int, Path(gt=0, description="id из /v1/subjects")]


@router.get("/subjects", summary="Предметы: средний ученика, динамика, периоды с оценками")
async def get_subjects(student: StudentDep) -> list[SubjectSummary]:
    return await student.subjects()


@router.get(
    "/subjects/{subject_id}",
    summary="Оценки по одному предмету: периоды, цель, оценки; чужой предмет — 404",
)
async def get_subject(subject_id: SubjectId, student: StudentDep) -> SubjectDetail:
    return await student.subject(subject_id)


@router.get("/subjects/{subject_id}/topics", summary="Темы предмета и ожидаемые результаты")
async def get_subject_topics(subject_id: SubjectId, student: StudentDep) -> list[SubjectTopic]:
    return await student.subject_topics(subject_id)
