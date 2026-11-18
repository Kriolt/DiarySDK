"""Родитель — владелец токена: свои данные, ученики, настройки, контакт."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response

from diarysdk.models.identity import ContactUpdate, Identity
from diarysdk.models.parent import Child, ParentMe
from diarysdk.models.settings import Settings, SettingsUpdate
from diarysdk.server.edge.auth import require_scope
from diarysdk.server.routes.deps import ParentDep

ContactId = Annotated[int, Path(gt=0, description="id контакта из /v1/parent/identity")]

router = APIRouter(prefix="/parent", tags=["родитель"])


@router.get("/me", summary="Профиль родителя: ФИО, тип, почта, телефон, срок токена")
async def get_me(parent: ParentDep) -> ParentMe:
    return await parent.me()


@router.get("/children", summary="Ученики родителя; их id — параметр child_id маршрутов ученика")
async def get_children(parent: ParentDep) -> list[Child]:
    return await parent.children()


@router.get("/identity", summary="Карточка родителя: документы, контакты, адреса")
async def get_identity(parent: ParentDep) -> Identity:
    return await parent.identity()


@router.get(
    "/avatar",
    summary="Аватарка родителя — сама картинка",
    response_class=Response,
    responses={200: {"content": {"image/*": {}}}, 404: {"description": "no_avatar"}},
)
async def get_avatar(parent: ParentDep) -> Response:
    avatar = await parent.avatar()
    return Response(content=avatar.content, media_type=avatar.content_type)


@router.get("/settings", summary="Настройки приложения родителя; общие для всех детей")
async def get_settings(parent: ParentDep) -> Settings:
    return await parent.settings()


# Запись не повторяется: после 502 и 504 неизвестно, принял ли её дневник.
@router.patch(
    "/settings",
    status_code=204,
    response_class=Response,
    summary="Изменить настройки приложения родителя",
    description="Правила те же, что у PATCH /v1/settings. Живьём не проверено.",
)
async def patch_settings(parent: ParentDep, update: SettingsUpdate) -> Response:
    await parent.update_settings(update)
    return Response(status_code=204)


@router.put(
    "/identity/contacts/{contact_id}",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(require_scope("write_profile"))],
    summary="Изменить адрес почты в контакте родителя",
    description=(
        "Нужен ключ с разрешением write_profile. Только почта: чужой id — 404, "
        "телефон — 422 contact_not_email. Живьём не проверено."
    ),
)
async def put_contact(parent: ParentDep, contact_id: ContactId, update: ContactUpdate) -> Response:
    await parent.update_contact(contact_id, update.value)
    return Response(status_code=204)
