"""Публичный API ядра: Diary, Login, LoginFlow, Student.

Работает с дневником напрямую, без сервера: Diary держит транспорт, шлюз и
кэш контекстов учеников, а бизнес-правила (периоды по умолчанию по Москве,
срок токена, общий дедлайн вызова, записи без повтора) — здесь.

Пароль, код, ответ на капчу и токен в repr, str и текстах исключений не
появляются.
"""

from __future__ import annotations

import asyncio
import weakref
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Literal, Self

import httpx
from pydantic import ValidationError

from diarysdk import _clock as clock
from diarysdk import _jwt as jwt
from diarysdk import _periods as periods
from diarysdk import _protocols as protocols
from diarysdk._context import ContextCache, hash_key
from diarysdk._gateway import DiaryGateway, write_started
from diarysdk._hosts import Hosts
from diarysdk._port import (
    FLOW_TTL,
    CaptchaChallenge,
    Ctx,
    EsiaSession,
    EsiaStep,
    MfaChallenge,
    ParentCtx,
    StudentContext,
)
from diarysdk._transport import Transport
from diarysdk._version import __version__
from diarysdk.errors import (
    BadCaptcha,
    BadCode,
    BadRequest,
    FlowExpired,
    TokenInvalid,
    UpstreamTimeout,
    WriteUncertain,
)
from diarysdk.models.auth import Captcha, LoginMfa
from diarysdk.models.avatar import Avatar
from diarysdk.models.certificates import Certificate
from diarysdk.models.curriculum import ControlWork, Curriculum, ProgramModule, SubjectTopic
from diarysdk.models.exams import Exam
from diarysdk.models.files import DiaryFile
from diarysdk.models.homework import Homework
from diarysdk.models.identity import ContactUpdate, Identity
from diarysdk.models.lessons import Lesson
from diarysdk.models.marks import AcademicDebt, FinalMark, Mark, MarkDetail
from diarysdk.models.me import Me
from diarysdk.models.notifications import Notification
from diarysdk.models.parent import Child, JournalAck, ParentMe
from diarysdk.models.periods import PeriodDay
from diarysdk.models.rating import Rating, RatingPoint, SubjectRating
from diarysdk.models.schedule import ScheduleItem
from diarysdk.models.school import School, SchoolTeacher
from diarysdk.models.settings import Settings, SettingsUpdate
from diarysdk.models.subjects import SubjectDetail, SubjectSummary
from diarysdk.token import Token

_STEP_NAMES = {"mfa": "код", "captcha": "ответ на капчу"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _mfa(challenge: MfaChallenge) -> LoginMfa:
    return LoginMfa(
        kind=challenge.kind,
        contact=challenge.contact,
        ttl=challenge.ttl,
        attempts_left=challenge.attempts_left,
    )


def _captcha(challenge: CaptchaChallenge) -> Captcha:
    return Captcha(
        kind=challenge.kind,
        image=challenge.image,
        image_type=challenge.image_type,
        question=challenge.question,
    )


@protocols.documented(protocols.DiaryLike)
class Diary:
    """Дневник «Моя школа» напрямую: `async with Diary() as diary`."""

    def __init__(
        self,
        *,
        hosts: Hosts | None = None,
        timeout: float = 15.0,
        deadline: float = 20.0,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        # timeout — на один запрос к дневнику, deadline — на весь вызов целиком
        # (контекст ученика, чтение, повтор GET).
        self._transport = Transport(
            user_agent=f"DiarySDK/{__version__}",
            total_timeout=timeout,
            connect_timeout=min(5.0, timeout),
            http=http,
        )
        self._gateway = DiaryGateway(self._transport, hosts or Hosts())
        self._deadline = deadline
        self._contexts = ContextCache(self._context)
        self._flows: weakref.WeakSet[LoginFlow] = weakref.WeakSet()
        # Отметки ознакомления: одна на (токен, ученик, неделя) одновременно.
        self._ack_locks: dict[tuple[str, int, date], list] = {}
        self._closed = False
        self.login = Login(self)

    def __repr__(self) -> str:
        return f"Diary(closed={self._closed})"

    async def __aenter__(self) -> Self:
        await self._transport.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        self._closed = True
        for flow in list(self._flows):
            flow._shut()
        await self._transport.close()

    def student(self, token: str | Token) -> Student:
        return Student(self, token if isinstance(token, Token) else Token(token))

    def parent(self, token: str | Token) -> Parent:
        return Parent(self, token if isinstance(token, Token) else Token(token))

    async def _context(self, token: str, child_id: int | None = None) -> StudentContext:
        try:
            # Срок нужен контексту; без него это не токен дневника — и спрашивать нечего.
            jwt.expires_at(token)
        except jwt.InvalidToken:
            raise TokenInvalid("Это не токен дневника") from None
        return await self._gateway.student_context(token, child_id)

    async def _timed[T](self, make: Callable[[], Awaitable[T]]) -> T:
        """Один вызов не дольше deadline: дальше — UpstreamTimeout."""
        if self._closed:
            raise RuntimeError("Diary закрыт")
        await self._transport.start()
        try:
            async with asyncio.timeout(self._deadline):
                return await make()
        except TimeoutError:
            raise UpstreamTimeout() from None


async def _guarded[T](diary: Diary, token: Token, run: Callable[[], Awaitable[T]]) -> T:
    """Вызов от имени токена, не дольше deadline.

    Если дедлайн вышел, когда запись уже отправлялась (шлюз отметил это в
    write_started), исход неизвестен — WriteUncertain, а не UpstreamTimeout.
    Дедлайн на чтении перед записью — обычный UpstreamTimeout.
    """
    if diary._closed:
        raise RuntimeError("Diary закрыт")
    # Просроченный токен не тратит запрос к дневнику.
    token.ensure_usable(_utcnow())
    await diary._transport.start()
    started: list[bool] = []
    marker = write_started.set(started)
    try:
        async with asyncio.timeout(diary._deadline):
            return await run()
    except TimeoutError:
        timeout = UpstreamTimeout()
        if started:
            raise WriteUncertain(cause=timeout) from None
        raise timeout from None
    finally:
        write_started.reset(marker)


def _check_child_id(child_id: int | None) -> None:
    """id ученика — положительное число, как требует и сервис (иначе 400 там)."""
    if child_id is not None and child_id <= 0:
        raise BadRequest("Неверные параметры запроса: child_id")


def _check_email(value: str) -> None:
    """Значение — не адрес почты (правило сервиса: 3-255 символов, одна @) —
    BadRequest до обращения к дневнику."""
    try:
        ContactUpdate(value=value)
    except ValidationError as error:
        # То же сообщение, что у сервиса на неверное тело запроса: имена полей,
        # а у ошибки всей модели (нет адреса почты) — «body».
        names = sorted({str(item["loc"][-1]) if item["loc"] else "body" for item in error.errors()})
        raise BadRequest(f"Неверные параметры запроса: {', '.join(names)}") from None


@protocols.documented(protocols.LoginLike)
class Login:
    """Вход: `diary.login`."""

    def __init__(self, diary: Diary) -> None:
        self._diary = diary

    def __repr__(self) -> str:
        return "Login()"

    async def password(self, login: str, password: str) -> Token:
        gateway = self._diary._gateway
        value = await self._diary._timed(lambda: gateway.password_login(login, password))
        return Token(value, method="password")

    async def esia(self, login: str, password: str) -> Token | LoginFlow:
        gateway = self._diary._gateway
        session, result = await self._diary._timed(lambda: gateway.esia_start(login, password))
        if isinstance(result, str):
            return Token(result, method="esia")
        flow = LoginFlow(self._diary, session, result)
        self._diary._flows.add(flow)
        return flow


@protocols.documented(protocols.LoginFlowLike)
class LoginFlow:
    """Вход через ЕСИА не закончен. Один объект живёт весь вход: после неверного
    ответа его `.mfa` и `.captcha` обновляются, и повторить можно на нём же."""

    def __init__(self, diary: Diary, session: EsiaSession, step: EsiaStep) -> None:
        self._diary = diary
        self._session: EsiaSession | None = session
        self._lock = asyncio.Lock()
        self.kind: Literal["mfa", "captcha"] = step.kind
        self.mfa: LoginMfa | None = None
        self.captcha: Captcha | None = None
        self.expires_at: datetime = _utcnow()
        self._apply(step)

    def __repr__(self) -> str:
        return f"LoginFlow(kind={self.kind!r}, expires_at={self.expires_at.isoformat()})"

    def _apply(self, step: EsiaStep) -> None:
        self.kind = step.kind
        self.mfa = _mfa(step.mfa) if step.mfa else None
        self.captcha = _captcha(step.captcha) if step.captcha else None
        # Вход живёт 5 минут с последнего шага.
        self.expires_at = _utcnow() + FLOW_TTL

    def _shut(self) -> None:
        session, self._session = self._session, None
        if session is not None:
            session.close()

    async def submit_code(self, code: str) -> Token | LoginFlow:
        gateway = self._diary._gateway
        return await self._step("mfa", lambda session: gateway.esia_code(session, code))

    async def answer_captcha(self, answer: str) -> Token | LoginFlow:
        gateway = self._diary._gateway
        return await self._step("captcha", lambda session: gateway.esia_captcha(session, answer))

    async def renew_captcha(self) -> LoginFlow:
        gateway = self._diary._gateway
        result = await self._step("captcha", gateway.esia_captcha_renew)
        if not isinstance(result, LoginFlow):
            raise TypeError("обновление капчи не даёт токена")
        return result

    async def close(self) -> None:
        self._shut()

    async def _step(
        self,
        expected: Literal["mfa", "captcha"],
        make: Callable[[EsiaSession], Awaitable[str | EsiaStep]],
    ) -> Token | LoginFlow:
        # Шаги одного входа идут по очереди: второй видит вход таким, каким его оставил первый.
        async with self._lock:
            session = self._session
            if session is None or session.waiting is None or _utcnow() >= self.expires_at:
                self._shut()
                raise FlowExpired()
            if session.waiting != expected:
                waiting = _STEP_NAMES.get(session.waiting, "другой шаг")
                raise BadRequest(f"Вход ждёт не этот шаг, а {waiting}")
            try:
                result = await self._diary._timed(lambda: make(session))
            except BadCode as error:
                self._retry(
                    error,
                    EsiaStep(mfa=error.step) if isinstance(error.step, MfaChallenge) else None,
                )
                raise
            except BadCaptcha as error:
                self._retry(
                    error,
                    EsiaStep(captcha=error.step)
                    if isinstance(error.step, CaptchaChallenge)
                    else None,
                )
                raise
            except BaseException:
                # Сбой, таймаут, блокировка: вход закрыт, начинать заново.
                self._shut()
                raise
            if isinstance(result, str):
                self._shut()
                return Token(result, method="esia")
            self._apply(result)
            return self

    def _retry(self, error: BadCode | BadCaptcha, step: EsiaStep | None) -> None:
        """Неверный ответ: вход жив, новый шаг — в самом потоке и в ошибке."""
        if step is not None:
            self._apply(step)
            error.step = self.mfa if isinstance(error, BadCode) else self.captcha
        else:
            self.expires_at = _utcnow() + FLOW_TTL
        error.flow = self


@protocols.documented(protocols.StudentLike)
class Student:
    """Запросы от имени одного ученика; создаётся `diary.student(token)`."""

    def __init__(self, diary: Diary, token: Token, child_id: int | None = None) -> None:
        self._diary = diary
        self._token = token
        # Выбранный ребёнок родителя; None — единственный ученик токена.
        self._child_id = child_id

    @property
    def token(self) -> Token:
        return self._token

    def __repr__(self) -> str:
        return f"Student(token={self._token!r})"

    async def _call[T](self, call: Callable[[Ctx], Awaitable[T]]) -> T:
        """Контекст ученика → вызов дневника, не дольше deadline.

        Если дедлайн вышел, когда запись уже отправлялась (шлюз отметил это в
        write_started), исход неизвестен — WriteUncertain, а не UpstreamTimeout.
        Дедлайн на чтении перед записью — обычный UpstreamTimeout.
        """
        diary, value = self._diary, self._token.value
        _check_child_id(self._child_id)

        async def run() -> T:
            student = await diary._contexts.get(value, self._child_id)
            return await call(Ctx(token=value, student=student))

        try:
            return await _guarded(diary, self._token, run)
        except TokenInvalid:
            # Дневник не принял токен — его контекст больше не годится.
            diary._contexts.evict(value, self._child_id)
            raise

    @property
    def _gateway(self) -> DiaryGateway:
        return self._diary._gateway

    @staticmethod
    def _today() -> date:
        return clock.today_msk()

    async def me(self) -> Me:
        return await self._call(self._gateway.me)

    async def avatar(self) -> Avatar:
        return await self._call(self._gateway.avatar)

    async def school(self) -> School:
        return await self._call(self._gateway.school)

    async def marks(self, start: date | None = None, end: date | None = None) -> list[Mark]:
        start, end = periods.marks_period(start, end, self._today())
        return await self._call(lambda ctx: self._gateway.marks(ctx, start, end))

    async def mark(self, mark_id: int) -> MarkDetail:
        return await self._call(lambda ctx: self._gateway.mark(ctx, mark_id))

    async def final_marks(self, year: int | None = None) -> list[FinalMark]:
        year = periods.final_marks_year(year, self._today())
        return await self._call(lambda ctx: self._gateway.final_marks(ctx, year))

    async def work_program(self, group_id: int) -> list[ProgramModule]:
        return await self._call(lambda ctx: self._gateway.work_program(ctx, group_id))

    async def subject_topics(self, subject_id: int) -> list[SubjectTopic]:
        return await self._call(lambda ctx: self._gateway.subject_topics(ctx, subject_id))

    async def control_works(
        self, start: date | None = None, end: date | None = None
    ) -> list[ControlWork]:
        start, end = periods.school_periods_period(start, end, self._today())
        return await self._call(lambda ctx: self._gateway.control_works(ctx, start, end))

    async def academic_debts(self, year: int | None = None) -> list[AcademicDebt]:
        year = periods.final_marks_year(year, self._today())
        return await self._call(lambda ctx: self._gateway.academic_debts(ctx, year))

    async def final_marks_file(
        self, year: int | None = None, orientation: Literal["portrait", "landscape"] = "portrait"
    ) -> DiaryFile:
        if orientation not in ("portrait", "landscape"):
            raise BadRequest("Неверные параметры запроса: orientation")
        year = periods.final_marks_year(year, self._today())
        return await self._call(lambda ctx: self._gateway.final_marks_file(ctx, year, orientation))

    async def certificates(self) -> list[Certificate]:
        return await self._call(self._gateway.certificates)

    async def school_teachers(self, name: str | None = None) -> list[SchoolTeacher]:
        return await self._call(lambda ctx: self._gateway.school_teachers(ctx, name))

    async def subjects(self) -> list[SubjectSummary]:
        return await self._call(self._gateway.subjects)

    async def rating(self, on: date | None = None, subject: int | None = None) -> Rating:
        day = on or self._today()
        return await self._call(lambda ctx: self._gateway.rating(ctx, day, subject))

    async def rating_subjects(self, on: date | None = None) -> list[SubjectRating]:
        day = on or self._today()
        return await self._call(lambda ctx: self._gateway.rating_subjects(ctx, day))

    async def rating_history(
        self, start: date | None = None, end: date | None = None
    ) -> list[RatingPoint]:
        start, end = periods.rating_history_period(start, end, self._today())
        return await self._call(lambda ctx: self._gateway.rating_history(ctx, start, end))

    async def schedule(
        self, start: date | None = None, end: date | None = None
    ) -> list[ScheduleItem]:
        start, end = periods.schedule_period(start, end, self._today())
        return await self._call(lambda ctx: self._gateway.schedule(ctx, start, end))

    async def lesson(self, lesson_id: int) -> Lesson:
        return await self._call(lambda ctx: self._gateway.lesson(ctx, lesson_id))

    async def homework(self, start: date | None = None, end: date | None = None) -> list[Homework]:
        start, end = periods.homework_period(start, end, self._today())
        return await self._call(lambda ctx: self._gateway.homework(ctx, start, end))

    async def homework_done(self, homework_id: int) -> None:
        await self._call(lambda ctx: self._gateway.set_homework_done(ctx, homework_id, True))

    async def homework_undone(self, homework_id: int) -> None:
        await self._call(lambda ctx: self._gateway.set_homework_done(ctx, homework_id, False))

    async def exams(self) -> list[Exam]:
        return await self._call(self._gateway.exams)

    async def settings(self) -> Settings:
        return await self._call(self._gateway.settings)

    async def update_settings(self, update: SettingsUpdate) -> None:
        await self._call(lambda ctx: self._gateway.update_settings(ctx, update))

    async def update_contact(self, contact_id: int, value: str) -> None:
        _check_email(value)
        await self._call(lambda ctx: self._gateway.update_contact(ctx, contact_id, value))

    async def identity(self) -> Identity:
        return await self._call(self._gateway.identity)

    async def notifications(self) -> list[Notification]:
        return await self._call(self._gateway.notifications)

    async def periods(self, start: date | None = None, end: date | None = None) -> list[PeriodDay]:
        start, end = periods.school_periods_period(start, end, self._today())
        return await self._call(lambda ctx: self._gateway.periods(ctx, start, end))

    async def subject(self, subject_id: int) -> SubjectDetail:
        return await self._call(lambda ctx: self._gateway.subject(ctx, subject_id))

    async def curriculum(self) -> Curriculum:
        return await self._call(self._gateway.curriculum)


@protocols.documented(protocols.ParentLike)
class Parent:
    """Родитель — владелец токена: свои данные и доступные ему ученики.
    Создаётся `diary.parent(token)` и сам запросов не делает."""

    def __init__(self, diary: Diary, token: Token) -> None:
        self._diary = diary
        self._token = token

    @property
    def token(self) -> Token:
        return self._token

    def __repr__(self) -> str:
        return f"Parent(token={self._token!r})"

    @property
    def _gateway(self) -> DiaryGateway:
        return self._diary._gateway

    async def _call[T](self, call: Callable[[ParentCtx], Awaitable[T]]) -> T:
        """Профиль родителя (каждый раз свежий: он и есть контекст) → вызов."""
        value = self._token.value

        async def run() -> T:
            try:
                jwt.expires_at(value)
            except jwt.InvalidToken:
                raise TokenInvalid("Это не токен дневника") from None
            parent = await self._gateway.parent_context(value)
            return await call(ParentCtx(token=value, parent=parent))

        return await _guarded(self._diary, self._token, run)

    def student(self, child_id: int) -> Student:
        return Student(self._diary, self._token, child_id)

    async def me(self) -> ParentMe:
        return await self._call(self._gateway.parent_me)

    async def identity(self) -> Identity:
        return await self._call(self._gateway.parent_identity)

    async def avatar(self) -> Avatar:
        return await self._call(self._gateway.parent_avatar)

    async def children(self) -> list[Child]:
        return await self._call(self._gateway.parent_children)

    async def settings(self) -> Settings:
        return await self._call(self._gateway.parent_settings)

    async def update_settings(self, update: SettingsUpdate) -> None:
        await self._call(lambda ctx: self._gateway.parent_update_settings(ctx, update))

    async def update_contact(self, contact_id: int, value: str) -> None:
        _check_email(value)
        await self._call(lambda ctx: self._gateway.parent_update_contact(ctx, contact_id, value))

    async def journal_acks(
        self, child_id: int, start: date | None = None, end: date | None = None
    ) -> list[JournalAck]:
        _check_child_id(child_id)
        start, end = periods.journal_period(start, end, clock.today_msk())
        return await self._call(
            lambda ctx: self._gateway.parent_journal_acks(ctx, child_id, start, end)
        )

    async def acknowledge_journal(self, child_id: int, week: date | None = None) -> None:
        _check_child_id(child_id)
        today = clock.today_msk()
        day = week or today
        if clock.week_bounds(day)[0] > clock.week_bounds(today)[0]:
            # Отметку нельзя отменить, а её видят учителя: будущую неделю не отмечаем.
            raise BadRequest("Неделя ещё не наступила: отметить её нельзя")
        monday = clock.week_bounds(day)[0]
        key = (hash_key(self._token.value), child_id, monday)
        locks = self._diary._ack_locks
        entry = locks.setdefault(key, [asyncio.Lock(), 0])
        entry[1] += 1
        try:
            # Второй одновременный вызов ждёт первый и видит его отметку: без второго POST.
            async with entry[0]:
                await self._call(
                    lambda ctx: self._gateway.parent_acknowledge_journal(ctx, child_id, day)
                )
        finally:
            # Блокировка живёт, пока ею кто-то пользуется (и ждущие тоже).
            entry[1] -= 1
            if entry[1] == 0:
                del locks[key]
