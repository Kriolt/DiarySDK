from typing import Annotated

from fastapi import APIRouter, Query

from diarysdk.models.rating import Rating, RatingPoint, SubjectRating
from diarysdk.server.routes.deps import StudentDep
from diarysdk.server.routes.params import OnDate, period_bound

router = APIRouter(tags=["рейтинг"])

From = period_bound("from", "1 сентября")
To = period_bound("to", "сегодня")
SubjectId = Annotated[
    int | None,
    Query(
        alias="subject",
        gt=0,
        description="ID предмета из /v1/subjects или /v1/rating/subjects — рейтинг по нему; "
        "по умолчанию — по всем предметам",
    ),
]


@router.get("/rating", summary="Рейтинг класса: место ученика, средний класса, одноклассники")
async def get_rating(student: StudentDep, on: OnDate = None, subject: SubjectId = None) -> Rating:
    return await student.rating(on, subject)


@router.get("/rating/subjects", summary="Место и средний ученика по каждому предмету")
async def get_rating_subjects(student: StudentDep, on: OnDate = None) -> list[SubjectRating]:
    return await student.rating_subjects(on)


@router.get("/rating/history", summary="Место в классе по дням")
async def get_rating_history(
    student: StudentDep, start: From = None, end: To = None
) -> list[RatingPoint]:
    return await student.rating_history(start, end)
