from fastapi import APIRouter, Response

from diarysdk.models.settings import Settings, SettingsUpdate
from diarysdk.server.routes.deps import StudentDep

router = APIRouter(tags=["настройки"])


@router.get("/settings", summary="Настройки приложения ученика; не задавались — все поля null")
async def get_settings(student: StudentDep) -> Settings:
    return await student.settings()


# Запись не повторяется: после 502 и 504 неизвестно, принял ли её дневник, —
# потребитель перечитывает /v1/settings.
@router.patch(
    "/settings",
    status_code=204,
    response_class=Response,
    summary="Изменить настройки приложения ученика",
    description=(
        "Меняет только поля, у которых в дневнике уже есть значение: группы нет — "
        "409 settings_missing, поле пусто — 409 setting_unset, текущее значение вне "
        "того, что сервис умеет записать, — 409 setting_unrestorable (в message "
        "имя поля). "
        "Прежнее значение читайте из GET /v1/settings до записи."
    ),
)
async def patch_settings(student: StudentDep, update: SettingsUpdate) -> Response:
    await student.update_settings(update)
    return Response(status_code=204)
