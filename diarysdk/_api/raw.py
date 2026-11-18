"""Запросы к дневнику, ответ которых разбирает mapping по сырому JSON.

Аватарка, ГИА, полные ДЗ, урок, оценка подробно, рейтинг по предмету, годовые
оценки, группа настроек и контакты. Идут через общий транспорт. Заголовки — по
таблице «Заголовки по семействам» спека.
"""

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from diarysdk._hosts import Hosts
from diarysdk._port import Owner, StudentContext
from diarysdk._transport import DiaryResponse
from diarysdk.errors import NotFound, UpstreamError, UpstreamFormat, WriteUncertain


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _family_web(token: str) -> dict[str, str]:
    return {"Auth-Token": token, "X-Mes-Subsystem": "familyweb", "Accept": "application/json"}


def _role_headers(student: StudentContext) -> dict[str, str]:
    """Роль владельца токена для family/web. Ученик — как у сайта (student, 1);
    родителю `X-Mes-RoleId: 1` дневник отвечает 401, а `parent` без него — 200."""
    if student.access == "parent":
        return {"Profile-Type": "parent"}
    return {"Profile-Type": "student", "X-Mes-RoleId": "1"}


def _family_mobile(token: str, profile_id: int) -> dict[str, str]:
    return {
        "Auth-Token": token,
        "X-Mes-Subsystem": "familymp",
        "Client-Type": "diary-mobile",
        "Profile-Id": str(profile_id),
        "Accept": "application/json",
    }


# Запись контакта: хост, путь и заголовки ВЫВЕДЕНЫ из бандла официального
# приложения (2026-08), живой запрос не наблюдался и не пробовался. Хост взят
# тот же, что у чтения карточки (hosts.dnevnik), а бандл называет для
# Подмосковья хост школы — если живой ответ покажет иное, менять только здесь.
def _contact_headers(token: str, profile_id: int) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Mes-Subsystem": "familymp",
        "Client-Type": "diary-mobile",
        "Profile-Id": str(profile_id),
        "Accept": "application/json",
    }


async def _write(transport, method: str, url: str, **kwargs: Any) -> DiaryResponse:
    """Запись без переходов по переадресации: клиент с переходами на 307/308 повторил бы
    PUT/POST/DELETE по новому адресу, а конец цепочки на 2xx выглядел бы
    успехом. Любой 3xx — WriteUncertain (причина — UpstreamError с этим кодом): запись
    ушла, а чем она кончилась, за переадресацией не видно."""
    response = await transport.send(method, url, follow_redirects=False, **kwargs)
    if 300 <= response.status < 400:
        raise WriteUncertain(cause=UpstreamError(upstream_status=response.status))
    return response


async def put_contact(
    transport,
    hosts: Hosts,
    token: str,
    student: Owner,
    contact_id: int,
    contact: dict[str, Any],
) -> DiaryResponse:
    """Записать контакт (PUT; тело приложения — ровно
    {id, person_id, type_id, data, default}). Транспорт запись не повторяет.
    Вывод запроса — см. комментарий над _contact_headers."""
    return await _write(
        transport,
        "PUT",
        f"{hosts.dnevnik}/api/persondata/v1/persons/{student.person_guid}/contacts/{contact_id}",
        headers=_contact_headers(token, student.profile_id),
        json=contact,
        call="contact.put",
    )


async def avatars(transport, hosts: Hosts, token: str, guid: str) -> Any:
    """Список аватарок [{id, url, default}] — так его берёт шапка сайта
    (Network). Без headerweb и X-Mes-HostId получали 403."""
    response = await transport.send(
        "GET",
        f"{hosts.dnevnik}/api/avatarmanagement/v1/{guid}",
        headers={
            **_bearer(token),
            "Auth-Token": token,
            "X-Mes-Subsystem": "headerweb",
            "X-Mes-HostId": "2",
        },
        call="avatar.list",
    )
    return response.json()


async def avatar(transport, hosts: Hosts, token: str, guid: str, image_id: int) -> DiaryResponse:
    """Картинка аватарки; без image_id дневник отвечал 406 (по наблюдениям)."""
    return await transport.send(
        "GET",
        f"{hosts.dnevnik}/avatars/{guid}",
        headers={**_bearer(token), "Accept": "image/*,*/*;q=0.8"},
        params={"image_id": str(image_id)},
        call="avatar",
    )


async def govexams(transport, hosts: Hosts, token: str, guid: str) -> Any:
    # Кука роли — как у сайта; и без неё получили 200, но список
    # был пуст, так что разницы не видно.
    response = await transport.send(
        "GET",
        f"{hosts.dnevnik}/portfolio/app/persons/{guid}/govexams/list/",
        headers={**_bearer(token), "Cookie": "aupd_current_role=4:1"},
        call="exams",
    )
    return response.json()


async def homeworks(
    transport,
    hosts: Hosts,
    token: str,
    student: StudentContext,
    start: date,
    end: date,
) -> Any:
    # Веб-путь family/web/v1/homeworks отдал те же записи в другом порядке.
    response = await transport.send(
        "GET",
        f"{hosts.school_api}/family/mobile/v1/homeworks",
        headers=_family_mobile(token, student.profile_id),
        params={
            "from": start.isoformat(),
            "to": end.isoformat(),
            "student_id": str(student.student_id),
        },
        call="homework",
    )
    return response.json()


async def homework_done(
    transport, hosts: Hosts, token: str, student: StudentContext, homework_id: int, done: bool
) -> DiaryResponse:
    """Отметить ДЗ выполненным (POST) или снять отметку (DELETE) — как
    официальное приложение: без тела, ID —
    homework_entry_student_id. Транспорт запись не повторяет."""
    return await _write(
        transport,
        "POST" if done else "DELETE",
        f"{hosts.school_api}/family/mobile/v1/homeworks/{homework_id}/done",
        headers=_family_mobile(token, student.profile_id),
        call="homework.done" if done else "homework.undone",
    )


async def lesson_schedule_item(
    transport, hosts: Hosts, token: str, student: StudentContext, lesson_id: int
) -> Any:
    """Урок разбирается лояльной моделью (mapping): если объявить пересчёт
    оценки целым, десятибалльная «9» (4.5) роняет весь урок."""
    response = await transport.send(
        "GET",
        f"{hosts.school_api}/family/mobile/v1/lesson_schedule_items/{lesson_id}",
        headers=_family_mobile(token, student.profile_id),
        params={"student_id": str(student.student_id), "type": "PLAN"},
        call="lesson",
    )
    return response.json()


async def rating_class_subject(
    transport, hosts: Hosts, token: str, student: StudentContext, subject_id: int, on: date
) -> Any:
    """Рейтинг класса по одному предмету: тот же rank/class, что и общий, но с
    subjectId (personId в camelCase)."""
    response = await transport.send(
        "GET",
        f"{hosts.dnevnik}/api/ej/rating/v1/rank/class",
        headers=_family_mobile(token, student.profile_id),
        params={
            "personId": student.person_guid,
            "classUnitId": str(student.class_unit_id),
            "date": on.isoformat(),
            "subjectId": str(subject_id),
        },
        call="rating.class.subject",
    )
    return response.json()


def academic_year_id(start_year: int) -> int:
    """ID учебного года журнала по году его начала. Наблюдение: 2023/24 — 11,
    2024/25 — 12, 2025/26 — 13."""
    return start_year - 2012


async def final_marks(
    transport, hosts: Hosts, token: str, student: StudentContext, start_year: int
) -> Any:
    """Годовые оценки за учебный год — запрос страницы сайта
    diary/marks/final-marks. Прошлые годы отдаёт по нынешним student_id и GUID;
    с is_year_marks_only=false ответ тот же."""
    response = await transport.send(
        "GET",
        f"{hosts.dnevnik}/api/family/web/v1/final_marks/v2",
        headers={
            **_bearer(token),
            **_family_web(token),
            "Profile-Id": str(student.profile_id),
            **_role_headers(student),
        },
        params={
            "person_id": student.person_guid,
            "academic_year_id": str(academic_year_id(start_year)),
            "student_id": str(student.student_id),
            "is_year_marks_only": "true",
        },
        call="final_marks",
    )
    return response.json()


class _Open(BaseModel):
    # Форма ответа — по другим клиентам, живой ответ ещё не снимали: лишнее
    # не отбрасываем, а недостающее не требуем.
    model_config = ConfigDict(extra="allow")


class MarkTeacher(_Open):
    last_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None


class MarkLessonInfo(_Open):
    topic: str | None = None
    schedule_item_id: int | None = None


class MarkDistributionInfo(_Open):
    value: str | None = None
    students: int | None = None
    percent: int | None = None


class MarkClassResults(_Open):
    total_students: int | None = None
    distribution: list[MarkDistributionInfo] | None = None


class MarkInfo(_Open):
    """Ответ family/mobile/v1/marks/{id} (форма — по другим клиентам)."""

    id: int | None = None
    value: str | None = None
    values: list[Any] | None = None
    comment: str | None = None
    weight: int | None = None
    point_date: Any = None
    control_form_name: str | None = None
    created_at: Any = None
    updated_at: Any = None
    date: Any = None
    is_exam: bool | None = None
    is_point: bool | None = None
    original_grade_system_type: str | None = None
    has_files: bool | None = None
    teacher: MarkTeacher | None = None
    lesson: MarkLessonInfo | None = None
    class_results: MarkClassResults | None = None
    criteria: Any = None
    history: Any = None
    result_files: Any = None


async def mark_info(
    transport, hosts: Hosts, token: str, student: StudentContext, mark_id: int
) -> MarkInfo:
    """Оценка подробно (family/mobile/v1/marks/{mark_id} со student_id). Владельца mark_id
    проверяет только дневник по student_id — поэтому он берётся из контекста
    токена, а не из запроса потребителя."""
    response = await transport.send(
        "GET",
        f"{hosts.school_api}/family/mobile/v1/marks/{mark_id}",
        headers=_family_mobile(token, student.profile_id),
        params={"student_id": str(student.student_id)},
        call="mark.info",
    )
    try:
        return MarkInfo.model_validate(response.json())
    except ValidationError as error:
        raise UpstreamFormat.from_validation(error) from None


# Только чтение: словарь общий для всех запросов, правка одного испортила бы все.
USER_SETTINGS_PARAMS: Mapping[str, str] = MappingProxyType(
    {"name": "settings_group_v1", "subsystem_id": "1"}
)


async def user_settings(
    transport, hosts: Hosts, token: str, student: Owner
) -> dict[str, Any] | None:
    """Группа настроек settings_group_v1 сырым JSON — тот же запрос, что
    у приложения. Группы нет (пустое тело, null, {} или 404
    дневника) — None: запись отличает «не было» от «пусто» и вернуть второе
    не может. Читается только эта группа: в том же хранилище под другими
    именами лежат чужие данные (спек «Отвергнуто»)."""
    try:
        response = await transport.send(
            "GET",
            f"{hosts.dnevnik}/api/usersettings/v1",
            headers=_family_mobile(token, student.profile_id),
            params=USER_SETTINGS_PARAMS,
            call="user.settings",
        )
    except NotFound:
        return None
    if not response.body.strip():
        return None
    data = response.json()
    if data is None or data == {}:
        return None
    if not isinstance(data, dict):
        raise UpstreamFormat(problems=["тело: ждали объект"])
    return data


async def put_user_settings(
    transport, hosts: Hosts, token: str, student: Owner, group: dict[str, Any]
) -> DiaryResponse:
    """Записать группу целиком (PUT, как у приложения): дневник принимает только весь объект.
    Транспорт запись не повторяет."""
    return await _write(
        transport,
        "PUT",
        f"{hosts.dnevnik}/api/usersettings/v1",
        headers=_family_mobile(token, student.profile_id),
        params=USER_SETTINGS_PARAMS,
        json=group,
        call="user.settings.put",
    )


def _aware_headers(token: str, parent_profile_id: int) -> dict[str, str]:
    """Как у сайта: familyweb и активный пользователь — родитель."""
    return {
        **_bearer(token),
        **_family_web(token),
        "Profile-Id": str(parent_profile_id),
        "Profile-Type": "parent",
    }


async def aware_journals(
    transport,
    hosts: Hosts,
    token: str,
    parent_profile_id: int,
    child_id: int,
    start: date,
    end: date,
) -> Any:
    """Отметки ознакомления родителя за недели [start, end] (сайт: diary, неделя)."""
    response = await transport.send(
        "GET",
        f"{hosts.dnevnik}/api/ej/core/family/v1/aware_journals",
        headers=_aware_headers(token, parent_profile_id),
        params={
            "week_from": start.isoformat(),
            "week_to": end.isoformat(),
            "student_profile_ids": str(child_id),
        },
        call="aware_journals",
    )
    return response.json()


async def post_aware_journal(
    transport, hosts: Hosts, token: str, parent_profile_id: int, body: dict[str, Any]
) -> DiaryResponse:
    """Отметить неделю «ознакомлен» (POST, тело как у сайта). Отмены у сайта нет."""
    return await _write(
        transport,
        "POST",
        f"{hosts.dnevnik}/api/ej/core/family/v1/aware_journals",
        headers=_aware_headers(token, parent_profile_id),
        json=body,
        call="aware_journals.post",
    )


# Учителя школы отдаются страницами; больше 20 страниц по 50 — уже не школа.
TEACHERS_PER_PAGE = 50
TEACHERS_MAX_PAGES = 20


def _ej_family(token: str, student: StudentContext) -> dict[str, str]:
    """Заголовки ej/core/family, как у сайта: familyweb и активный пользователь."""
    return {
        **_bearer(token),
        **_family_web(token),
        "Profile-Id": str(student.profile_id),
        **_role_headers(student),
    }


async def teacher_profiles(
    transport, hosts: Hosts, token: str, student: StudentContext, name: str | None, page: int
) -> Any:
    params = {
        "school_id": str(student.school_id),
        "with_virtual_teachers": "false",
        "full_list_teachers": "true",
        "per_page": str(TEACHERS_PER_PAGE),
        "page": str(page),
    }
    if name:
        params["user_sub_name"] = name
    response = await transport.send(
        "GET",
        f"{hosts.dnevnik}/api/ej/core/family/v1/teacher_profiles",
        headers=_ej_family(token, student),
        params=params,
        call="teacher_profiles",
    )
    return response.json()


async def academic_debts(
    transport, hosts: Hosts, token: str, student: StudentContext, start_year: int
) -> Any:
    """Задолженности класса за учебный год — как у сайта (по class_unit_ids)."""
    response = await transport.send(
        "GET",
        f"{hosts.dnevnik}/api/ej/core/family/v1/academic_debts",
        headers=_ej_family(token, student),
        params={
            "class_unit_ids": str(student.class_unit_id),
            "academic_year_id": str(academic_year_id(start_year)),
        },
        call="academic_debts",
    )
    return response.json()


async def work_program(
    transport, hosts: Hosts, token: str, student: StudentContext, group_id: int
) -> Any:
    """Рабочая программа учебной группы (сайт: «Рабочие программы учебного плана»)."""
    response = await transport.send(
        "GET",
        f"{hosts.dnevnik}/api/family/web/v1/programs/lesson_plan",
        headers=_ej_family(token, student),
        params={
            "student_id": str(student.student_id),
            "group_id": str(group_id),
            "school_id": str(student.school_id),
        },
        call="work_program",
    )
    return response.json()


async def thematic_frames(
    transport, hosts: Hosts, token: str, student: StudentContext, subject_id: int
) -> Any:
    response = await transport.send(
        "GET",
        f"{hosts.dnevnik}/api/ej/plan/family/v1/thematic_frames",
        headers=_ej_family(token, student),
        params={"subject_id": str(subject_id), "student_profile_id": str(student.student_id)},
        call="thematic_frames",
    )
    return response.json()


async def test_lessons(
    transport, hosts: Hosts, token: str, student: StudentContext, start: date, end: date
) -> Any:
    response = await transport.send(
        "GET",
        f"{hosts.dnevnik}/api/ej/plan/family/v1/test_lessons/period",
        headers=_ej_family(token, student),
        params={
            "student_profile_id": str(student.student_id),
            "from": start.isoformat(),
            "to": end.isoformat(),
            "student_person_id": student.person_guid,
        },
        call="test_lessons",
    )
    return response.json()


async def final_marks_file(
    transport, hosts: Hosts, token: str, student: StudentContext, start_year: int, orientation: str
) -> DiaryResponse:
    """PDF итоговых оценок за учебный год — кнопка «Скачать» сайта."""
    return await transport.send(
        "GET",
        f"{hosts.dnevnik}/api/family/web/v1/final_marks/file",
        headers={**_ej_family(token, student), "Accept": "*/*"},
        params={
            "student_id": str(student.student_id),
            "academic_year_id": str(academic_year_id(start_year)),
            "orientation": orientation,
        },
        call="final_marks.file",
    )


# Справки: страницы по 10, как у сайта; больше 10 страниц — уже не справки ученика.
CERTIFICATES_PER_PAGE = 10
CERTIFICATES_MAX_PAGES = 10


async def certificate_statuses(transport, hosts: Hosts, token: str, student: StudentContext) -> Any:
    response = await transport.send(
        "GET",
        f"{hosts.dnevnik}/api/certificates/family/v1/certificates/statuses",
        headers=_ej_family(token, student),
        call="certificates.statuses",
    )
    return response.json()


async def certificates(
    transport,
    hosts: Hosts,
    token: str,
    student: StudentContext,
    start: date,
    end: date,
    offset: int,
) -> Any:
    """Заявки на справки за [start, end]; studentId — GUID ученика (как у сайта)."""
    response = await transport.send(
        "GET",
        f"{hosts.dnevnik}/api/certificates/family/v1/certificates",
        headers=_ej_family(token, student),
        params={
            "requestDateFrom": start.isoformat(),
            "requestDateTo": end.isoformat(),
            "studentId": student.person_guid,
            "limit": str(CERTIFICATES_PER_PAGE),
            "offset": str(offset),
        },
        call="certificates",
    )
    return response.json()
