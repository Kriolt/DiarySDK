from fastapi import APIRouter, Response

from diarysdk.models.me import Me
from diarysdk.server.routes.deps import StudentDep

router = APIRouter(tags=["ученик"])


@router.get("/me", summary="Кто ученик: ФИО, GUID, школа, класс, профиль, кружки")
async def get_me(student: StudentDep) -> Me:
    return await student.me()


@router.get(
    "/me/avatar",
    summary="Аватарка ученика — сама картинка",
    response_class=Response,
    responses={200: {"content": {"image/*": {}}}, 404: {"description": "no_avatar"}},
)
async def get_avatar(student: StudentDep) -> Response:
    avatar = await student.avatar()
    return Response(content=avatar.content, media_type=avatar.content_type)
