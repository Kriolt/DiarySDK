"""Реализация интерфейса Diary: запрос к дневнику (_api), затем mapping.

Методы fetch_* — слой запросов: что именно спросить у дневника. Ими же
пользуются и тесты, поэтому фикстуры получаются ровно из тех запросов, что
делает сервис.
"""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import replace
from datetime import date
from typing import Any

from diarysdk import _clock as clock
from diarysdk import _jwt as jwt
from diarysdk._api import raw
from diarysdk._api.mobile import MobileAPI
from diarysdk._api.web import WebAPI
from diarysdk._hosts import Hosts
from diarysdk._login import esia as login_esia
from diarysdk._login import password as login_steps
from diarysdk._mapping import avatar as avatar_mapping
from diarysdk._mapping import curriculum as curriculum_mapping
from diarysdk._mapping import ej as ej_mapping
from diarysdk._mapping import exams as exams_mapping
from diarysdk._mapping import final_marks as final_marks_mapping
from diarysdk._mapping import homework as homework_mapping
from diarysdk._mapping import identity as identity_mapping
from diarysdk._mapping import journal as journal_mapping
from diarysdk._mapping import lessons as lessons_mapping
from diarysdk._mapping import marks as marks_mapping
from diarysdk._mapping import me as me_mapping
from diarysdk._mapping import notifications as notifications_mapping
from diarysdk._mapping import parent as parent_mapping
from diarysdk._mapping import periods as periods_mapping
from diarysdk._mapping import rating as rating_mapping
from diarysdk._mapping import schedule as schedule_mapping
from diarysdk._mapping import school as school_mapping
from diarysdk._mapping import settings as settings_mapping
from diarysdk._mapping import subjects as subjects_mapping
from diarysdk._mapping.context import student_context
from diarysdk._port import (
    Ctx,
    EsiaSession,
    EsiaStep,
    Owner,
    ParentContext,
    ParentCtx,
    StudentContext,
)
from diarysdk._transport import DiaryResponse, RatingOff
from diarysdk._wire.mobile import (
    Marks,
    Notification,
    ParallelCurriculum,
    PeriodsSchedules,
    SchoolInfo,
    SubjectMarksForSubject,
    SubjectsMarks,
)
from diarysdk._wire.rating import RatingRankClass, RatingRankShort, RatingRankSubject
from diarysdk._wire.web import EventsResponse, PersonData, WebFamilyProfile
from diarysdk.errors import (
    NoAvatar,
    NotForRole,
    NotFound,
    SettingsMissing,
    TokenInvalid,
    UpstreamError,
    UpstreamFormat,
    WriteUncertain,
)
from diarysdk.models.avatar import Avatar
from diarysdk.models.curriculum import Curriculum
from diarysdk.models.exams import Exam
from diarysdk.models.homework import Homework
from diarysdk.models.identity import Identity
from diarysdk.models.lessons import Lesson
from diarysdk.models.marks import AcademicDebt, FinalMark, Mark, MarkDetail
from diarysdk.models.me import Me
from diarysdk.models.notifications import Notification as ContractNotification
from diarysdk.models.parent import Child, JournalAck, ParentMe
from diarysdk.models.periods import PeriodDay
from diarysdk.models.rating import Rating, RatingPoint, SubjectRating
from diarysdk.models.schedule import ScheduleItem
from diarysdk.models.school import School, SchoolTeacher
from diarysdk.models.settings import Settings, SettingsUpdate
from diarysdk.models.subjects import SubjectDetail, SubjectSummary

# Полный expand: с health_status и причинами
# пропусков — сервис отдаёт всё, что дневник знает об ученике.
EVENTS_EXPAND = "marks,homework,absence_reason_id,health_status,nonattendance_reason_id"


def _refused(response: DiaryResponse) -> bool:
    """На отметку ДЗ, её снятие и повтор дневник отвечает {"success": true}
    (по наблюдениям). Тело разбираем только ради success: false, остальное —
    успех по коду 2xx."""
    if not response.body.lstrip().startswith(b"{"):
        return False
    try:
        data = response.json()
    except UpstreamFormat:
        return False
    return isinstance(data, dict) and data.get("success") is False


def _esia(session: EsiaSession) -> login_esia.EsiaState:
    # Сессию создаёт только esia_start этого же gateway.
    if not isinstance(session, login_esia.EsiaState):
        raise TypeError("сессия входа не от этого дневника")
    return session


# Статусы дневника, после которых неизвестно, применилась ли запись.
_UNCERTAIN_STATUSES = {502, 504}


# Отметка «запись пошла»: вызывающий кладёт сюда список, _write ставит в него True.
# По ней видно, на чтении или на самой отправке вышел дедлайн.
write_started: ContextVar[list[bool] | None] = ContextVar("diary_write_started", default=None)


async def _write[T](send: Awaitable[T]) -> T:
    """Запись: сеть, таймаут, 502 и 504 — исход неизвестен (WriteUncertain), повтора нет.

    Остальные отказы (400, 401, 403, 500…) значат, что запись не прошла, и идут как есть.
    Ответ 2xx с неразобранным телом — запись принята, это не неопределённость.
    """
    if (mark := write_started.get()) is not None:
        mark.append(True)
    try:
        return await send
    except UpstreamFormat:
        raise
    except UpstreamError as error:
        if error.upstream_status is None or error.upstream_status in _UNCERTAIN_STATUSES:
            raise WriteUncertain(cause=error) from None
        raise


def _not_for_parent(ctx: Ctx) -> None:
    """Аватарку и экзамены дневник отдаёт только владельцу токена: родителю — нет
    (живой ответ: 403 «user_id не принадлежит пользователю», 469 «не найден»)."""
    if ctx.student.access == "parent":
        raise NotForRole(role="parent")


class DiaryGateway:
    def __init__(
        self, transport, hosts: Hosts, *, today: Callable[[], date] = clock.today_msk
    ) -> None:
        self._transport = transport
        self._hosts = hosts
        self._today = today

    def _web(self, token: str) -> WebAPI:
        return WebAPI(self._transport, self._hosts, token)

    def _mobile(self, token: str) -> MobileAPI:
        return MobileAPI(self._transport, self._hosts, token)

    # --- методы контракта (интерфейс Diary) -------------------------------

    async def password_login(self, login: str, password: str) -> str:
        return await login_steps.password_login(self._transport, self._hosts, login, password)

    async def esia_start(self, login: str, password: str) -> tuple[EsiaSession, str | EsiaStep]:
        return await login_esia.esia_start(self._transport, self._hosts, login, password)

    async def esia_code(self, session: EsiaSession, code: str) -> str | EsiaStep:
        return await login_esia.esia_code(self._transport, self._hosts, _esia(session), code)

    async def esia_captcha(self, session: EsiaSession, answer: str) -> str | EsiaStep:
        return await login_esia.esia_captcha(self._transport, self._hosts, _esia(session), answer)

    async def esia_captcha_renew(self, session: EsiaSession) -> EsiaStep:
        return await login_esia.esia_captcha_renew(self._transport, self._hosts, _esia(session))

    async def student_context(self, token: str, child_id: int | None = None) -> StudentContext:
        profile = await self.fetch_profile(token)
        context = student_context(profile, jwt.expires_at(token), child_id)
        return replace(context, profile=profile)

    async def _profile(self, ctx: Ctx) -> WebFamilyProfile:
        """Профиль для me/identity: уже разобранный при сборке контекста или свежий."""
        return ctx.student.profile or await self.fetch_profile(ctx.token)

    async def me(self, ctx: Ctx) -> Me:
        profile = await self._profile(ctx)
        return me_mapping.me(profile, ctx.student.expires_at, self._today(), ctx.student.student_id)

    # --- родитель ------------------------------------------------------

    async def parent_context(self, token: str) -> ParentContext:
        profile = await self.fetch_profile(token)
        guid = jwt.decode_payload(token).get("msh")
        return parent_mapping.parent_context(
            profile, jwt.expires_at(token), guid if isinstance(guid, str) and guid else None
        )

    async def parent_me(self, ctx: ParentCtx) -> ParentMe:
        return parent_mapping.me(ctx.parent.profile, ctx.parent.expires_at)

    async def parent_children(self, ctx: ParentCtx) -> list[Child]:
        return parent_mapping.children(ctx.parent.profile)

    async def parent_identity(self, ctx: ParentCtx) -> Identity:
        card = None
        guid = ctx.parent.person_guid
        if guid is not None:
            try:
                card = await self._web(ctx.token).get_person_data(person_id=guid)
            except NotFound:
                card = None
        return identity_mapping.owner_identity(ctx.parent.profile.profile, card)

    async def parent_avatar(self, ctx: ParentCtx) -> Avatar:
        if ctx.parent.person_guid is None:
            raise NoAvatar()
        return await self._avatar_of(ctx.token, ctx.parent.person_guid)

    async def parent_settings(self, ctx: ParentCtx) -> Settings:
        return await self._settings_of(ctx.token, ctx.parent)

    async def parent_update_settings(self, ctx: ParentCtx, update: SettingsUpdate) -> None:
        await self._update_settings_of(ctx.token, ctx.parent, update)

    async def parent_update_contact(self, ctx: ParentCtx, contact_id: int, value: str) -> None:
        if ctx.parent.person_guid is None:
            raise NotFound("Карточка родителя не найдена")
        await self._update_contact_of(ctx.token, ctx.parent, contact_id, value)

    def _child_of(self, ctx: ParentCtx, child_id: int) -> int:
        """id ученика родителя или NotFound — до запросов про этого ученика."""
        if not any(child.id == child_id for child in ctx.parent.profile.children or []):
            raise NotFound("Такого ученика у этого токена нет")
        return child_id

    async def parent_journal_acks(
        self, ctx: ParentCtx, child_id: int, start: date, end: date
    ) -> list[JournalAck]:
        child = self._child_of(ctx, child_id)
        data = await raw.aware_journals(
            self._transport, self._hosts, ctx.token, ctx.parent.profile_id, child, start, end
        )
        return journal_mapping.acks(data)

    async def parent_acknowledge_journal(self, ctx: ParentCtx, child_id: int, week: date) -> None:
        """Отметка недели; уже отмечена — второй POST не уходит (отмены у сайта нет)."""
        monday, sunday = clock.week_bounds(week)
        acks = await self.parent_journal_acks(ctx, child_id, monday, sunday)
        if journal_mapping.has_week(acks, child_id, monday):
            return
        body = {
            "created_at": journal_mapping.stamp(clock.now_msk()),
            "week": monday.isoformat(),
            "parent_profile_id": ctx.parent.profile_id,
            "student_profile_id": child_id,
        }
        response = await _write(
            raw.post_aware_journal(
                self._transport, self._hosts, ctx.token, ctx.parent.profile_id, body
            )
        )
        if _refused(response):
            raise UpstreamError(upstream_status=response.status)

    async def school_teachers(self, ctx: Ctx, name: str | None) -> list[SchoolTeacher]:
        """Все страницы справочника учителей школы (не больше TEACHERS_MAX_PAGES)."""
        result: list[SchoolTeacher] = []
        for page in range(1, raw.TEACHERS_MAX_PAGES + 1):
            data = await raw.teacher_profiles(
                self._transport, self._hosts, ctx.token, ctx.student, name, page
            )
            result += ej_mapping.teachers(data)
            if not isinstance(data, list) or len(data) < raw.TEACHERS_PER_PAGE:
                break
        return result

    async def academic_debts(self, ctx: Ctx, year: int) -> list[AcademicDebt]:
        data = await raw.academic_debts(self._transport, self._hosts, ctx.token, ctx.student, year)
        return ej_mapping.academic_debts(data, ctx.student.student_id)

    async def schedule(self, ctx: Ctx, start: date, end: date) -> list[ScheduleItem]:
        return schedule_mapping.schedule(await self.fetch_events(ctx, start, end))

    async def school(self, ctx: Ctx) -> School:
        return school_mapping.school(await self.fetch_school(ctx))

    async def avatar(self, ctx: Ctx) -> Avatar:
        _not_for_parent(ctx)
        return await self._avatar_of(ctx.token, ctx.student.person_guid)

    async def _avatar_of(self, token: str, guid: str) -> Avatar:
        try:
            response = await self._fetch_avatar(token, guid)
        except NotFound:
            raise NoAvatar() from None
        if response is None or not response.body:
            raise NoAvatar()
        content_type = response.content_type or ""
        if not content_type.startswith("image/"):
            # Не картинка — скорее страница ошибки портала; её наружу не отдаём.
            raise UpstreamFormat(
                problems=[f"avatar: ждали image/*, пришло {content_type or 'без типа'}"]
            )
        return Avatar(content=response.body, content_type=content_type)

    async def exams(self, ctx: Ctx) -> list[Exam]:
        _not_for_parent(ctx)
        return exams_mapping.exams(await self.fetch_exams(ctx))

    async def final_marks(self, ctx: Ctx, year: int) -> list[FinalMark]:
        return final_marks_mapping.final_marks(await self.fetch_final_marks(ctx, year))

    async def homework(self, ctx: Ctx, start: date, end: date) -> list[Homework]:
        return homework_mapping.homework(await self.fetch_homework(ctx, start, end))

    async def set_homework_done(self, ctx: Ctx, homework_id: int, done: bool) -> None:
        response = await _write(self.send_homework_done(ctx, homework_id, done))
        if _refused(response):
            # 2xx, но запись не принята: для потребителя — ошибка дневника.
            raise UpstreamError(upstream_status=response.status)

    async def settings(self, ctx: Ctx) -> Settings:
        return await self._settings_of(ctx.token, ctx.student)

    async def _settings_of(self, token: str, owner: Owner) -> Settings:
        return settings_mapping.settings(
            await raw.user_settings(self._transport, self._hosts, token, owner)
        )

    async def update_settings(self, ctx: Ctx, update: SettingsUpdate) -> None:
        await self._update_settings_of(ctx.token, ctx.student, update)

    async def _update_settings_of(self, token: str, owner: Owner, update: SettingsUpdate) -> None:
        group = await raw.user_settings(self._transport, self._hosts, token, owner)
        if group is None:
            raise SettingsMissing()
        body = settings_mapping.merged(group, update)
        try:
            response = await _write(
                raw.put_user_settings(self._transport, self._hosts, token, owner, body)
            )
        except TokenInvalid as error:
            # Тем же токеном только что прочитали группу: отказ — про право на
            # запись, а не про токен. Контекст токена не выбрасываем.
            raise UpstreamError(upstream_status=error.status) from None
        if _refused(response):
            raise UpstreamError(upstream_status=response.status)

    async def update_contact(self, ctx: Ctx, contact_id: int, value: str) -> None:
        await self._update_contact_of(ctx.token, ctx.student, contact_id, value)

    async def _update_contact_of(
        self, token: str, owner: Owner, contact_id: int, value: str
    ) -> None:
        # Ошибки чтения карточки (в том числе 401/403) идут как есть: контекст
        # токена при них выбрасывается, как у любого чтения.
        card = await self._web(token).get_person_data(person_id=owner.person_guid)
        contact = identity_mapping.email_contact(card, contact_id)
        # Тело как у приложения: ровно пять полей. Ничего больше (статус
        # проверки, type, неизвестные поля) назад не отправляется.
        body = {
            "id": contact.get("id"),
            "person_id": contact.get("person_id"),
            "type_id": contact.get("type_id"),
            "data": value,
            "default": contact.get("default"),
        }
        try:
            response = await _write(
                raw.put_contact(self._transport, self._hosts, token, owner, contact_id, body)
            )
        except TokenInvalid as error:
            # Тем же токеном только что прочитали карточку: отказ — про право на
            # запись, а не про токен. Контекст токена не выбрасываем.
            raise UpstreamError(upstream_status=error.status) from None
        if _refused(response):
            raise UpstreamError(upstream_status=response.status)

    async def identity(self, ctx: Ctx) -> Identity:
        profile = await self._profile(ctx)
        # Карточка нужна всегда: в ней документы, место рождения, история
        # обучения, а не только СНИЛС на случай пустого профиля.
        try:
            card = await self.fetch_person_data(ctx)
        except NotFound:
            # Карточки нет.
            card = None
        except TokenInvalid as error:
            if error.status != 403:
                raise
            # 403: ученику карточка не видна. Поля карточки тогда null, а не
            # ошибка всего ответа; контекст токена не выбрасывается. Сбои дневника
            # (таймаут, сеть, 5xx, формат) — не «нет карточки» и идут наружу.
            card = None
        return identity_mapping.identity(profile, card, ctx.student.student_id)

    async def lesson(self, ctx: Ctx, lesson_id: int) -> Lesson:
        return lessons_mapping.lesson(await self.fetch_lesson(ctx, lesson_id))

    async def marks(self, ctx: Ctx, start: date, end: date) -> list[Mark]:
        return marks_mapping.marks(await self.fetch_marks(ctx, start, end))

    async def mark(self, ctx: Ctx, mark_id: int) -> MarkDetail:
        return marks_mapping.mark_detail(await self.fetch_mark_info(ctx, mark_id))

    async def subjects(self, ctx: Ctx) -> list[SubjectSummary]:
        return subjects_mapping.subjects(await self.fetch_subjects(ctx))

    async def subject(self, ctx: Ctx, subject_id: int) -> SubjectDetail:
        # Дневник ищет предмет по имени, а потребитель знает ID: имя — из того
        # же списка, что отдаёт /v1/subjects. Чужого ID в списке нет — 404 без
        # второго запроса.
        listed = (await self.fetch_subjects(ctx)).payload or []
        name = next((item.subject_name for item in listed if item.subject_id == subject_id), None)
        if name is None:
            raise NotFound()
        return subjects_mapping.subject_detail(
            await self.fetch_subject_marks_for_subject(ctx, name)
        )

    async def rating(self, ctx: Ctx, on: date, subject_id: int | None = None) -> Rating:
        try:
            if subject_id is None:
                ranks = await self.fetch_rating_class(ctx, on)
            else:
                ranks = rating_mapping.class_ranks(
                    await self.fetch_rating_class_subject(ctx, subject_id, on)
                )
        except RatingOff:
            return Rating.disabled()
        return rating_mapping.rating(ranks, ctx.student.person_guid, on)

    async def rating_subjects(self, ctx: Ctx, on: date) -> list[SubjectRating]:
        try:
            return rating_mapping.subject_ratings(await self.fetch_rating_subjects(ctx, on))
        except RatingOff:
            return []

    async def rating_history(self, ctx: Ctx, start: date, end: date) -> list[RatingPoint]:
        try:
            return rating_mapping.history(await self.fetch_rating_short(ctx, start, end))
        except RatingOff:
            return []

    async def notifications(self, ctx: Ctx) -> list[ContractNotification]:
        return notifications_mapping.notifications(await self.fetch_notifications(ctx))

    async def periods(self, ctx: Ctx, start: date, end: date) -> list[PeriodDay]:
        return periods_mapping.periods(await self.fetch_periods_schedules(ctx, start, end))

    async def curriculum(self, ctx: Ctx) -> Curriculum:
        curriculum_id = ctx.student.parallel_curriculum_id
        if curriculum_id is None:
            # Плана у ученика нет: дневник не спрашиваем.
            raise NotFound()
        return curriculum_mapping.curriculum(await self.fetch_curriculum(ctx, curriculum_id))

    # --- слой запросов ---------------------------------------------------

    async def fetch_profile(self, token: str) -> WebFamilyProfile:
        return await self._web(token).get_family_web_profile()

    async def fetch_school(self, ctx: Ctx) -> SchoolInfo:
        s = ctx.student
        return await self._mobile(ctx.token).get_school_info(
            profile_id=s.profile_id, school_id=s.school_id, class_unit_id=s.class_unit_id
        )

    async def fetch_marks(self, ctx: Ctx, start: date, end: date) -> Marks:
        s = ctx.student
        return await self._mobile(ctx.token).get_marks(
            student_id=s.student_id, profile_id=s.profile_id, from_date=start, to_date=end
        )

    async def fetch_mark_info(self, ctx: Ctx, mark_id: int) -> raw.MarkInfo:
        return await raw.mark_info(self._transport, self._hosts, ctx.token, ctx.student, mark_id)

    async def fetch_subjects(self, ctx: Ctx) -> SubjectsMarks:
        s = ctx.student
        return await self._mobile(ctx.token).get_subjects_marks(
            profile_id=s.profile_id, student_id=s.student_id
        )

    async def fetch_rating_class(self, ctx: Ctx, on: date) -> list[RatingRankClass]:
        s = ctx.student
        return await self._mobile(ctx.token).get_rating_rank_class(
            profile_id=s.profile_id,
            person_id=s.person_guid,
            class_unit_id=s.class_unit_id,
            on=on,
        )

    async def fetch_rating_class_subject(self, ctx: Ctx, subject_id: int, on: date) -> Any:
        return await raw.rating_class_subject(
            self._transport, self._hosts, ctx.token, ctx.student, subject_id, on
        )

    async def fetch_rating_subjects(self, ctx: Ctx, on: date) -> list[RatingRankSubject]:
        s = ctx.student
        return await self._mobile(ctx.token).get_rating_rank_subjects(
            profile_id=s.profile_id, person_id=s.person_guid, on=on
        )

    async def fetch_rating_short(self, ctx: Ctx, start: date, end: date) -> list[RatingRankShort]:
        s = ctx.student
        return await self._mobile(ctx.token).get_rating_rank_short(
            profile_id=s.profile_id, person_id=s.person_guid, begin_date=start, end_date=end
        )

    async def fetch_events(
        self, ctx: Ctx, start: date, end: date, *, expand: str = EVENTS_EXPAND
    ) -> EventsResponse:
        return await self._web(ctx.token).get_events(
            person_id=ctx.student.person_guid,
            mes_role="student",
            begin_date=start,
            end_date=end,
            expand=expand,
        )

    async def fetch_lesson(self, ctx: Ctx, lesson_id: int) -> Any:
        # Урок разбирается лояльной моделью (см. raw.lesson_schedule_item):
        # десятибалльные оценки не роняют ответ.
        return await raw.lesson_schedule_item(
            self._transport, self._hosts, ctx.token, ctx.student, lesson_id
        )

    async def fetch_homework(self, ctx: Ctx, start: date, end: date) -> Any:
        return await raw.homeworks(self._transport, self._hosts, ctx.token, ctx.student, start, end)

    async def send_homework_done(self, ctx: Ctx, homework_id: int, done: bool) -> DiaryResponse:
        return await raw.homework_done(
            self._transport, self._hosts, ctx.token, ctx.student, homework_id, done
        )

    async def fetch_exams(self, ctx: Ctx) -> Any:
        return await raw.govexams(self._transport, self._hosts, ctx.token, ctx.student.person_guid)

    async def fetch_final_marks(self, ctx: Ctx, year: int) -> Any:
        return await raw.final_marks(self._transport, self._hosts, ctx.token, ctx.student, year)

    async def fetch_person_data(self, ctx: Ctx) -> PersonData:
        return await self._web(ctx.token).get_person_data(person_id=ctx.student.person_guid)

    async def fetch_avatar(self, ctx: Ctx) -> DiaryResponse | None:
        return await self._fetch_avatar(ctx.token, ctx.student.person_guid)

    async def _fetch_avatar(self, token: str, guid: str) -> DiaryResponse | None:
        """Как сайт: список аватарок, затем картинка основной; None — их нет."""
        listing = await raw.avatars(self._transport, self._hosts, token, guid)
        image_id = avatar_mapping.avatar_id(listing)
        if image_id is None:
            return None
        return await raw.avatar(self._transport, self._hosts, token, guid, image_id)

    # --- источники вне контракта --------------------

    async def fetch_notifications(self, ctx: Ctx) -> list[Notification]:
        s = ctx.student
        return await self._mobile(ctx.token).get_notifications(
            student_id=s.student_id, profile_id=s.profile_id
        )

    async def fetch_curriculum(self, ctx: Ctx, curriculum_id: int) -> ParallelCurriculum:
        s = ctx.student
        return await self._mobile(ctx.token).get_programs_parallel_curriculum(
            curriculum_id=curriculum_id, profile_id=s.profile_id, student_id=s.student_id
        )

    async def fetch_periods_schedules(
        self, ctx: Ctx, start: date, end: date
    ) -> list[PeriodsSchedules]:
        s = ctx.student
        return await self._mobile(ctx.token).get_periods_schedules(
            student_id=s.student_id, profile_id=s.profile_id, from_date=start, to_date=end
        )

    async def fetch_subject_marks_for_subject(
        self, ctx: Ctx, subject_name: str
    ) -> SubjectMarksForSubject:
        s = ctx.student
        return await self._mobile(ctx.token).get_subject_marks_for_subject(
            student_id=s.student_id, profile_id=s.profile_id, subject_name=subject_name
        )

    async def fetch_user_settings(self, ctx: Ctx) -> dict[str, Any] | None:
        return await raw.user_settings(self._transport, self._hosts, ctx.token, ctx.student)

    async def send_user_settings(self, ctx: Ctx, group: dict[str, Any]) -> DiaryResponse:
        return await raw.put_user_settings(
            self._transport, self._hosts, ctx.token, ctx.student, group
        )
