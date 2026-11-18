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
from diarysdk._context import ContextCache
from diarysdk._gateway import DiaryGateway, write_started
from diarysdk._hosts import Hosts
from diarysdk._port import (
    FLOW_TTL,
    CaptchaChallenge,
    Ctx,
    EsiaSession,
    EsiaStep,
    MfaChallenge,
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
from diarysdk.models.curriculum import Curriculum
from diarysdk.models.exams import Exam
from diarysdk.models.homework import Homework
from diarysdk.models.identity import ContactUpdate, Identity
from diarysdk.models.lessons import Lesson
from diarysdk.models.marks import FinalMark, Mark, MarkDetail
from diarysdk.models.me import Me
from diarysdk.models.notifications import Notification
from diarysdk.models.periods import PeriodDay
from diarysdk.models.rating import Rating, RatingPoint, SubjectRating
from diarysdk.models.schedule import ScheduleItem
from diarysdk.models.school import School
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
        """Закрыть соединения и незаконченные входы через ЕСИА."""
        self._closed = True
        for flow in list(self._flows):
            flow._shut()
        await self._transport.close()

    def student(self, token: str | Token) -> Student:
        return Student(self, token if isinstance(token, Token) else Token(token))

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
        """Токен или, если ЕСИА просит код или капчу, поток входа."""
        gateway = self._diary._gateway
        session, result = await self._diary._timed(lambda: gateway.esia_start(login, password))
        if isinstance(result, str):
            return Token(result, method="esia")
        flow = LoginFlow(self._diary, session, result)
        self._diary._flows.add(flow)
        return flow


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
        """Код из SMS или приложения. Неверный — `BadCode` с новым шагом в `.step`;
        вход жив, `.mfa` обновлён, можно повторить."""
        gateway = self._diary._gateway
        return await self._step("mfa", lambda session: gateway.esia_code(session, code))

    async def answer_captcha(self, answer: str) -> Token | LoginFlow:
        """Ответ на капчу. Неверный — `BadCaptcha` со свежей капчей в `.step`."""
        gateway = self._diary._gateway
        return await self._step("captcha", lambda session: gateway.esia_captcha(session, answer))

    async def renew_captcha(self) -> LoginFlow:
        """Другая картинка капчи."""
        gateway = self._diary._gateway
        result = await self._step("captcha", gateway.esia_captcha_renew)
        if not isinstance(result, LoginFlow):
            raise TypeError("обновление капчи не даёт токена")
        return result

    async def close(self) -> None:
        """Закрыть вход; повторный вызов не ошибка."""
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
        diary = self._diary
        token = self._token
        if diary._closed:
            raise RuntimeError("Diary закрыт")
        # Просроченный токен не тратит запрос к дневнику.
        token.ensure_usable(_utcnow())
        await diary._transport.start()
        started: list[bool] = []
        marker = write_started.set(started)
        try:
            async with asyncio.timeout(diary._deadline):
                student = await diary._contexts.get(token.value, self._child_id)
                return await call(Ctx(token=token.value, student=student))
        except TimeoutError:
            timeout = UpstreamTimeout()
            if started:
                raise WriteUncertain(cause=timeout) from None
            raise timeout from None
        except TokenInvalid:
            # Дневник не принял токен — его контекст больше не годится.
            diary._contexts.evict(token.value, self._child_id)
            raise
        finally:
            write_started.reset(marker)

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
        """Заменить адрес почты в контакте ученика.

        Значение — не адрес почты (правило сервиса: 3-255 символов, одна @) —
        BadRequest до обращения к дневнику; контакт не почта — UnsupportedContact.
        """
        try:
            ContactUpdate(value=value)
        except ValidationError as error:
            # То же сообщение, что у сервиса на неверное тело запроса: имена полей,
            # а у ошибки всей модели (нет адреса почты) — «body».
            names = sorted(
                {str(item["loc"][-1]) if item["loc"] else "body" for item in error.errors()}
            )
            raise BadRequest(f"Неверные параметры запроса: {', '.join(names)}") from None
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
