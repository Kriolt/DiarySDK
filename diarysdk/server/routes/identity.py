from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response

from diarysdk.models.identity import ContactUpdate, Identity
from diarysdk.server.edge.auth import require_scope
from diarysdk.server.routes.deps import StudentDep

ContactId = Annotated[int, Path(gt=0, description="id контакта из /v1/identity")]

router = APIRouter(tags=["ученик"])


@router.get(
    "/identity",
    summary="ФИО, дата рождения, контакты и СНИЛС ученика и его представителей",
    description=(
        "Для ответов на запросы администрации. Разграничения прав внутри сервера нет: "
        "поля видит любой действующий ключ, доступ разграничивает потребитель."
    ),
)
async def get_identity(student: StudentDep) -> Identity:
    return await student.identity()


# Запись не повторяется: после 502 и 504 неизвестно, принял ли её дневник, —
# потребитель перечитывает /v1/identity. Разрешение проверяется до разбора
# тела и до похода в дневник.
@router.put(
    "/identity/contacts/{contact_id}",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(require_scope("write_profile"))],
    summary="Изменить адрес почты в контакте ученика",
    description=(
        "Нужен ключ с разрешением write_profile. Только почта: чужой id — 404, "
        "телефон — 422 contact_not_email. Эндпоинт не подтверждён и до проверки на живом "
        "ответе может снять с контакта статус проверки; вернуть его нельзя."
    ),
)
async def put_contact(
    student: StudentDep, contact_id: ContactId, update: ContactUpdate
) -> Response:
    await student.update_contact(contact_id, update.value)
    return Response(status_code=204)
