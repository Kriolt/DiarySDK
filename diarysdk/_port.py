"""Интерфейс к дневнику на языке нашего контракта.

Исключения — в `diarysdk.errors`. Исключения HTTP-клиента и
ValidationError pydantic за пределы ядра не выходят: транспорт и _api
переводят их в наши. В текст исключений не попадает ни тело ответа дневника,
ни URL — в них ID ученика и ПДн.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal, Protocol

from diarysdk.errors import UnsupportedStep

if TYPE_CHECKING:
    from datetime import date

    from diarysdk._wire.web import WebFamilyProfile
    from diarysdk.models.avatar import Avatar
    from diarysdk.models.curriculum import Curriculum
    from diarysdk.models.exams import Exam
    from diarysdk.models.homework import Homework
    from diarysdk.models.identity import Identity
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


# Сколько живёт вход через ЕСИА с последнего шага.
FLOW_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class MfaChallenge:
    """ЕСИА ждёт код: из SMS (sms) или из приложения (totp) или из мессенджера MAX (max)."""

    kind: Literal["sms", "totp", "max"]
    # Маскированный телефон, как его показывает ЕСИА. Это контакт
    # пользователя: в repr его нет.
    contact: str | None = field(repr=False)
    # Сколько секунд живёт код и сколько попыток ввода осталось.
    ttl: int
    attempts_left: int


@dataclass(frozen=True)
class CaptchaChallenge:
    """ЕСИА сочла вход аномалией и ждёт ответа: картинка или вопрос."""

    kind: Literal["image", "question"]
    image: bytes | None = field(default=None, repr=False)
    image_type: str | None = None
    question: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class EsiaStep:
    """Вход не закончен: нужен код или ответ на капчу."""

    mfa: MfaChallenge | None = None
    captcha: CaptchaChallenge | None = None

    @property
    def kind(self) -> Literal["mfa", "captcha"]:
        return "mfa" if self.mfa is not None else "captcha"


class EsiaSession(Protocol):
    """Состояние начатого входа через ЕСИА между запросами потребителя:
    только куки esia и authedu и что ЕСИА попросила. Логина, пароля, кода и
    ответа на капчу в нём нет."""

    @property
    def waiting(self) -> Literal["mfa", "captcha"] | None:
        """Какой шаг ждёт поток; None — поток закрыт."""
        ...

    def close(self) -> None:
        """Стереть куки и всё, что ЕСИА попросила. Повторный вызов безвреден."""
        ...


def unsupported_step(name: object, *, kind_of: str = "", hint: str = "") -> UnsupportedStep:
    """ЕСИА просит шаг, которого сервис не умеет (push, ЭЦП, новая капча).

    Название шага попадает в ответ, только если похоже на название (буквы,
    цифры, точка, дефис, до 64 знаков), иначе «неизвестный»: так в ответ не
    пройдёт ничего, что могло прийти от пользователя. Совет — наш текст.
    """
    shown = name if isinstance(name, str) and _STEP_NAME.fullmatch(name) else "неизвестный"
    return UnsupportedStep(what=f"{kind_of} {shown}" if kind_of else shown, hint=hint)


_STEP_NAME = re.compile(r"[\w.\-]{1,64}")


@dataclass(frozen=True)
class StudentContext:
    """ID ученика в обоих пространствах дневника. Кэшируется по хэшу токена."""

    student_id: int
    person_guid: str
    profile_id: int
    class_unit_id: int
    school_id: int
    expires_at: datetime
    # Учебный план параллели; в профиле его может не быть.
    parallel_curriculum_id: int | None = None
    # Разобранный профиль, из которого собран контекст: только у свежесобранного,
    # чтобы me/identity не запрашивали его второй раз. В кэш он не попадает.
    profile: WebFamilyProfile | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class Ctx:
    """Контекст одного запроса: токен и ученик. Токен не попадает в repr."""

    token: str = field(repr=False)
    student: StudentContext


class Diary(Protocol):
    """Дневник на языке контракта. Реализация — _gateway.DiaryGateway."""

    async def password_login(self, login: str, password: str) -> str:
        """Логин и пароль портала → JWT; отказ — BadCredentials."""
        ...

    async def esia_start(self, login: str, password: str) -> tuple[EsiaSession, str | EsiaStep]:
        """Логин и пароль Госуслуг → JWT или следующий шаг. С JWT сессия уже
        закрыта; со шагом её держит хранилище потоков."""
        ...

    async def esia_code(self, session: EsiaSession, code: str) -> str | EsiaStep:
        """Код MFA → JWT или следующий шаг; неверный код — BadCode."""
        ...

    async def esia_captcha(self, session: EsiaSession, answer: str) -> str | EsiaStep:
        """Ответ на капчу → JWT или следующий шаг; неверный — BadCaptcha."""
        ...

    async def esia_captcha_renew(self, session: EsiaSession) -> EsiaStep:
        """Новая капча вместо текущей."""
        ...

    async def student_context(self, token: str) -> StudentContext: ...

    async def me(self, ctx: Ctx) -> Me: ...

    async def schedule(self, ctx: Ctx, start: date, end: date) -> list[ScheduleItem]: ...

    async def school(self, ctx: Ctx) -> School: ...

    async def avatar(self, ctx: Ctx) -> Avatar: ...

    async def exams(self, ctx: Ctx) -> list[Exam]: ...

    async def final_marks(self, ctx: Ctx, year: int) -> list[FinalMark]: ...

    async def homework(self, ctx: Ctx, start: date, end: date) -> list[Homework]: ...

    async def set_homework_done(self, ctx: Ctx, homework_id: int, done: bool) -> None: ...

    async def identity(self, ctx: Ctx) -> Identity: ...

    async def lesson(self, ctx: Ctx, lesson_id: int) -> Lesson: ...

    async def marks(self, ctx: Ctx, start: date, end: date) -> list[Mark]: ...

    async def mark(self, ctx: Ctx, mark_id: int) -> MarkDetail: ...

    async def subjects(self, ctx: Ctx) -> list[SubjectSummary]: ...

    async def subject(self, ctx: Ctx, subject_id: int) -> SubjectDetail: ...

    async def rating(self, ctx: Ctx, on: date, subject_id: int | None = None) -> Rating: ...

    async def rating_subjects(self, ctx: Ctx, on: date) -> list[SubjectRating]: ...

    async def rating_history(self, ctx: Ctx, start: date, end: date) -> list[RatingPoint]: ...

    async def notifications(self, ctx: Ctx) -> list[Notification]: ...

    async def periods(self, ctx: Ctx, start: date, end: date) -> list[PeriodDay]: ...

    async def curriculum(self, ctx: Ctx) -> Curriculum: ...

    async def settings(self, ctx: Ctx) -> Settings: ...

    async def update_contact(self, ctx: Ctx, contact_id: int, value: str) -> None:
        """Прочитать карточку, найти контакт ученика по id, заменить адрес и
        записать контакт: в теле ровно {id, person_id, type_id, data, default},
        остальные поля прочитанного контакта не уходят. Чужой id — NotFound,
        не почта — UnsupportedContact, в обоих случаях без записи."""
        ...

    async def update_settings(self, ctx: Ctx, update: SettingsUpdate) -> None:
        """Прочитать группу, заменить переданные поля, записать целиком. Группы
        нет — SettingsMissing, поле пусто — SettingNotSet, в обоих случаях без записи."""
        ...
