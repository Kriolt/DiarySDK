"""Методы ученика: тонкие обёртки над описаниями из _core."""

from __future__ import annotations

import inspect
import logging
from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING, Any

from diarysdk.errors import TokenExpired
from diarysdk.models.curriculum import ControlWork, Curriculum, ProgramModule, SubjectTopic
from diarysdk.models.exams import Exam
from diarysdk.models.homework import Homework
from diarysdk.models.identity import Identity
from diarysdk.models.lessons import Lesson
from diarysdk.models.marks import AcademicDebt, FinalMark, Mark, MarkDetail
from diarysdk.models.me import Me
from diarysdk.models.notifications import Notification
from diarysdk.models.periods import PeriodDay
from diarysdk.models.rating import Rating, RatingPoint, SubjectRating
from diarysdk.models.schedule import ScheduleItem
from diarysdk.models.school import School, SchoolTeacher
from diarysdk.models.settings import Settings, SettingsUpdate
from diarysdk.models.subjects import SubjectDetail, SubjectSummary
from diarysdk.remote import _core
from diarysdk.remote._core import Avatar, Request
from diarysdk.token import Token

if TYPE_CHECKING:
    from diarysdk.remote.client import RemoteDiary


log = logging.getLogger("diarysdk.remote")


def _hook_failed(expired: TokenExpired, failure: Exception) -> None:
    """Хук упал: потребитель всё равно получит TokenExpired, а сбой хука виден рядом.

    Ошибка хука не подменяет TokenExpired (по ней решают, звать ли ученика
    входить) и не затирает его __context__: тип сбоя добавляется заметкой
    (add_note) и пишется в журнал, без текста: в нём может быть что угодно, в
    том числе токен.
    """
    expired.add_note(f"Хук on_token_expired упал: {type(failure).__name__}")
    log.warning("Хук on_token_expired упал: %s", type(failure).__name__)


def as_token(token: str | Token) -> Token:
    return token if isinstance(token, Token) else Token(token)


class RemoteStudent:
    """Запросы от имени одного ученика; создаётся `diary.student(token)`."""

    def __init__(self, diary: RemoteDiary, token: str | Token, child_id: int | None = None) -> None:
        self._diary = diary
        # Ученик родителя: уходит параметром child_id в каждый запрос.
        self._child_id = child_id
        self._token = as_token(token)

    @property
    def token(self) -> Token:
        return self._token

    def __repr__(self) -> str:
        return f"RemoteStudent(token={self._token!r})"

    async def _call(self, spec: Request) -> Any:
        if self._child_id is not None:
            spec = replace(spec, params={**spec.params, "child_id": self._child_id})
        try:
            return await self._diary._send(spec, self._token.value)
        except TokenExpired as expired:
            # Один раз на каждый отказ: потребитель просит ученика войти заново.
            hook = self._diary._config.on_token_expired
            if hook is not None:
                try:
                    result = hook(self._token)
                    if inspect.isawaitable(result):
                        await result
                except Exception as failure:
                    _hook_failed(expired, failure)
            raise

    async def me(self) -> Me:
        return await self._call(_core.me())

    async def avatar(self) -> Avatar:
        return await self._call(_core.avatar())

    async def school(self) -> School:
        return await self._call(_core.school())

    async def marks(self, start: date | None = None, end: date | None = None) -> list[Mark]:
        return await self._call(_core.marks(start, end))

    async def mark(self, mark_id: int) -> MarkDetail:
        return await self._call(_core.mark(mark_id))

    async def final_marks(self, year: int | None = None) -> list[FinalMark]:
        return await self._call(_core.final_marks(year))

    async def work_program(self, group_id: int) -> list[ProgramModule]:
        return await self._call(_core.work_program(group_id))

    async def subject_topics(self, subject_id: int) -> list[SubjectTopic]:
        return await self._call(_core.subject_topics(subject_id))

    async def control_works(
        self, start: date | None = None, end: date | None = None
    ) -> list[ControlWork]:
        return await self._call(_core.control_works(start, end))

    async def academic_debts(self, year: int | None = None) -> list[AcademicDebt]:
        return await self._call(_core.academic_debts(year))

    async def school_teachers(self, name: str | None = None) -> list[SchoolTeacher]:
        return await self._call(_core.school_teachers(name))

    async def subjects(self) -> list[SubjectSummary]:
        return await self._call(_core.subjects())

    async def rating(self, on: date | None = None, subject: int | None = None) -> Rating:
        return await self._call(_core.rating(on, subject))

    async def rating_subjects(self, on: date | None = None) -> list[SubjectRating]:
        return await self._call(_core.rating_subjects(on))

    async def rating_history(
        self, start: date | None = None, end: date | None = None
    ) -> list[RatingPoint]:
        return await self._call(_core.rating_history(start, end))

    async def schedule(
        self, start: date | None = None, end: date | None = None
    ) -> list[ScheduleItem]:
        return await self._call(_core.schedule(start, end))

    async def lesson(self, lesson_id: int) -> Lesson:
        return await self._call(_core.lesson(lesson_id))

    async def homework(self, start: date | None = None, end: date | None = None) -> list[Homework]:
        return await self._call(_core.homework(start, end))

    async def homework_done(self, homework_id: int) -> None:
        await self._call(_core.homework_done(homework_id, True))

    async def homework_undone(self, homework_id: int) -> None:
        await self._call(_core.homework_done(homework_id, False))

    async def exams(self) -> list[Exam]:
        return await self._call(_core.exams())

    async def settings(self) -> Settings:
        return await self._call(_core.settings())

    async def update_settings(self, update: SettingsUpdate) -> None:
        await self._call(_core.update_settings(update))

    async def update_contact(self, contact_id: int, value: str) -> None:
        """Заменить адрес почты в контакте ученика. Нужен ключ с разрешением
        write_profile (иначе ForbiddenScope); не почта — UnsupportedContact."""
        await self._call(_core.update_contact(contact_id, value))

    async def identity(self) -> Identity:
        return await self._call(_core.identity())

    async def notifications(self) -> list[Notification]:
        return await self._call(_core.notifications())

    async def periods(self, start: date | None = None, end: date | None = None) -> list[PeriodDay]:
        return await self._call(_core.periods(start, end))

    async def subject(self, subject_id: int) -> SubjectDetail:
        return await self._call(_core.subject(subject_id))

    async def curriculum(self) -> Curriculum:
        return await self._call(_core.curriculum())
