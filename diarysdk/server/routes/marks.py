from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Response

from diarysdk.models.marks import AcademicDebt, FinalMark, Mark, MarkDetail
from diarysdk.server.routes.deps import StudentDep
from diarysdk.server.routes.params import period_bound

router = APIRouter(tags=["оценки"])

MarkId = Annotated[int, Path(gt=0, description="id из /v1/marks")]
From = period_bound("from", "1 сентября")
To = period_bound("to", "сегодня; период не длиннее 366 дней")
# ID учебного года журнала — год начала минус 2012, поэтому не раньше 2013.
Year = Annotated[
    int | None,
    Query(
        ge=2013,
        description="год начала учебного года: 2024 — это 2024/25; по умолчанию — текущий",
    ),
]


@router.get("/marks", summary="Оценки за период")
async def get_marks(student: StudentDep, start: From = None, end: To = None) -> list[Mark]:
    return await student.marks(start, end)


@router.get("/final-marks", summary="Годовые оценки за учебный год, в том числе прошлые")
async def get_final_marks(student: StudentDep, year: Year = None) -> list[FinalMark]:
    return await student.final_marks(year)


@router.get(
    "/marks/{mark_id}", summary="Оценка подробно: учитель, урок, итоги класса; нет такой — 404"
)
async def get_mark(mark_id: MarkId, student: StudentDep) -> MarkDetail:
    return await student.mark(mark_id)


@router.get(
    "/academic-debts",
    summary="Академические задолженности ученика за учебный год",
    description="Форма ответа дневника живьём не подтверждена (ответы были пустыми).",
)
async def get_academic_debts(student: StudentDep, year: Year = None) -> list[AcademicDebt]:
    return await student.academic_debts(year)


@router.get(
    "/final-marks/file",
    summary="PDF итоговых оценок за учебный год",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def get_final_marks_file(
    student: StudentDep,
    year: Year = None,
    orientation: Annotated[
        Literal["portrait", "landscape"], Query(description="ориентация страницы")
    ] = "portrait",
) -> Response:
    file = await student.final_marks_file(year, orientation)
    headers = {
        "Content-Disposition": f'attachment; filename="{file.filename or "final-marks.pdf"}"'
    }
    return Response(content=file.content, media_type=file.content_type, headers=headers)
