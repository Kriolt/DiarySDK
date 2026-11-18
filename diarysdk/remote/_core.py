"""Общее удалённого клиента: описание запросов и разбор ответов.

Каждый эндпоинт описывается один раз как `Request`; клиент только исполняет
его, а решения о повторах и ошибках принимает `exchange`.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError

from diarysdk.errors import (
    DiaryError,
    NetworkError,
    UnsupportedStep,
    UpstreamFormat,
    WriteUncertain,
    from_response,
)
from diarysdk.models.auth import LoginStep
from diarysdk.models.auth import TokenResponse as TokenModel
from diarysdk.models.avatar import Avatar
from diarysdk.models.curriculum import Curriculum
from diarysdk.models.exams import Exam
from diarysdk.models.homework import Homework
from diarysdk.models.identity import Identity
from diarysdk.models.lessons import Lesson
from diarysdk.models.marks import FinalMark, Mark, MarkDetail
from diarysdk.models.me import Me
from diarysdk.models.notifications import Notification
from diarysdk.models.parent import Child, JournalAck, ParentMe
from diarysdk.models.periods import PeriodDay
from diarysdk.models.rating import Rating, RatingPoint, SubjectRating
from diarysdk.models.schedule import ScheduleItem
from diarysdk.models.school import School
from diarysdk.models.settings import Settings, SettingsUpdate
from diarysdk.models.subjects import SubjectDetail, SubjectSummary

# Пауза перед единственным повтором чтения — как у сервиса к дневнику.
RETRY_PAUSE = 0.5
_RETRY_STATUSES = frozenset({502, 503, 504})
# После этих статусов неизвестно, применил ли дневник запись.
_UNCERTAIN_STATUSES = frozenset({502, 504})


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    params: dict[str, Any] = field(default_factory=dict)
    # Тип для pydantic (`list[Mark]`), `bytes` — сырое тело, None — без тела (204).
    model: Any = None
    # Тело JSON; в repr не попадает: там пароль или код.
    body: dict[str, Any] | None = field(default=None, repr=False)
    # Шаг входа: не чтение, но и не запись ДЗ — при сбое «начните вход заново».
    login: bool = False

    @property
    def idempotent(self) -> bool:
        return self.method == "GET"

    @property
    def uncertain(self) -> bool:
        """После сбоя неизвестно, применил ли дневник запрос (запись ДЗ)."""
        return not self.idempotent and not self.login


class LoginResult:
    """model запроса входа: 200 — Token, 202 — LoginStep."""


@cache
def _adapter(model: Any) -> TypeAdapter:
    return TypeAdapter(model)


def build_params(params: dict[str, Any]) -> dict[str, str]:
    # None — «по умолчанию на сервере»; даты уходят как ISO.
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else str(value)
        for key, value in params.items()
        if value is not None
    }


def parse_success(spec: Request, response: httpx.Response) -> Any:
    if spec.model is None:
        return None
    if spec.model is Avatar:
        return Avatar(response.content, response.headers.get("content-type", ""))
    model = spec.model
    if model is LoginResult:
        model = LoginStep if response.status_code == 202 else TokenModel
    if model is LoginStep:
        _check_step(response)
    try:
        return _adapter(model).validate_json(response.content)
    except ValidationError as error:
        # Контракт разошёлся с версией клиента: поля значений в сообщение не кладём.
        raise UpstreamFormat(
            "Ответ сервиса не соответствует модели клиента, обновите diarysdk",
            status=response.status_code,
        ) from error


_KNOWN_STEPS = frozenset({"mfa", "captcha"})


def _check_step(response: httpx.Response) -> None:
    """Шаг входа, которого клиент не знает, — не поломка формата, а новый сценарий."""
    try:
        step = json.loads(response.content).get("step")
    except ValueError, AttributeError:
        return  # дальше разберёт валидация модели
    if isinstance(step, str) and step not in _KNOWN_STEPS:
        raise UnsupportedStep(
            "Сервис просит шаг входа, которого этот клиент не знает: обновите diarysdk",
            status=response.status_code,
        )


def parse_error(response: httpx.Response) -> DiaryError:
    try:
        body = json.loads(response.content)
    except ValueError:
        body = None
    return from_response(response.status_code, body, response.headers.get("Retry-After"))


def can_retry(spec: Request, error: DiaryError, *, retried: bool) -> bool:
    return (
        spec.idempotent
        and not retried
        and (error.status is None or error.status in _RETRY_STATUSES)
    )


def rate_wait(error: DiaryError, max_rate_wait: float, *, waited: bool) -> float | None:
    """Сколько ждать до повтора после 429, или None — отдать RateLimited.

    429 значит «не принято до обработки», поэтому ждём и для записи тоже.
    """
    if waited or error.status != 429 or error.retry_after is None:
        return None
    return error.retry_after if error.retry_after <= max_rate_wait else None


def network_error(spec: Request, cause: Exception) -> DiaryError:
    if spec.uncertain:
        return _uncertain(NetworkError(), cause)
    return NetworkError()


def _write_outcome_unknown(response: httpx.Response) -> bool:
    """Исход записи неизвестен: сервис сам так сказал (`"uncertain": true`) или
    ответ не его (прокси, HTML): что было в дневнике, не видно. Сервис без этого
    поля в теле ошибки — определённый отказ."""
    try:
        body = json.loads(response.content)
    except ValueError:
        return True
    if not isinstance(body, dict) or not isinstance(body.get("error"), str):
        return True
    return body.get("uncertain") is True


def final_error(spec: Request, error: DiaryError, response: httpx.Response) -> DiaryError:
    if spec.uncertain and error.status in _UNCERTAIN_STATUSES and _write_outcome_unknown(response):
        return _uncertain(error, error)
    return error


def _uncertain(error: DiaryError, source: BaseException) -> WriteUncertain:
    result = WriteUncertain(cause=error, status=error.status)
    result.__cause__ = source
    return result


@dataclass(frozen=True)
class Send:
    """Действие для клиента: отправить запрос и вернуть ответ или TransportError."""


@dataclass(frozen=True)
class Sleep:
    """Действие для клиента: подождать `seconds` и вернуть None."""

    seconds: float


Action = Send | Sleep


def exchange(spec: Request, max_rate_wait: float) -> Generator[Action, Any, Any]:
    """Все решения об отправке, повторах и ожидании в одном месте.

    Клиент только исполняет ввод-вывод: на `Send` отправляют
    запрос и передают в генератор `httpx.Response` или пойманный
    `httpx.TransportError`, на `Sleep` ждут и передают None. Результат —
    `StopIteration.value`, ошибка поднимается из генератора.
    """
    retried = rate_waited = False
    while True:
        outcome = yield Send()
        if isinstance(outcome, httpx.TransportError):
            error = network_error(spec, outcome)
            if can_retry(spec, error, retried=retried):
                retried = True
                yield Sleep(RETRY_PAUSE)
                continue
            raise error from outcome
        if outcome.is_success:
            return parse_success(spec, outcome)
        error = parse_error(outcome)
        wait = rate_wait(error, max_rate_wait, waited=rate_waited)
        if wait is not None:
            rate_waited = True
            yield Sleep(wait)
            continue
        if can_retry(spec, error, retried=retried):
            retried = True
            yield Sleep(RETRY_PAUSE)
            continue
        raise final_error(spec, error, outcome)


# Описания эндпоинтов /v1. Имена параметров — как в запросе (`from`, `to`),
# даты — `date`, не строки: ISO собирает build_params.
def me() -> Request:
    return Request("GET", "/v1/me", model=Me)


def avatar() -> Request:
    return Request("GET", "/v1/me/avatar", model=Avatar)


def school() -> Request:
    return Request("GET", "/v1/school", model=School)


def marks(start: date | None, end: date | None) -> Request:
    return Request("GET", "/v1/marks", {"from": start, "to": end}, list[Mark])


def mark(mark_id: int) -> Request:
    return Request("GET", f"/v1/marks/{mark_id}", model=MarkDetail)


def final_marks(year: int | None) -> Request:
    return Request("GET", "/v1/final-marks", {"year": year}, list[FinalMark])


def subjects() -> Request:
    return Request("GET", "/v1/subjects", model=list[SubjectSummary])


def rating(on: date | None, subject: int | None) -> Request:
    return Request("GET", "/v1/rating", {"date": on, "subject": subject}, Rating)


def rating_subjects(on: date | None) -> Request:
    return Request("GET", "/v1/rating/subjects", {"date": on}, list[SubjectRating])


def rating_history(start: date | None, end: date | None) -> Request:
    return Request("GET", "/v1/rating/history", {"from": start, "to": end}, list[RatingPoint])


def schedule(start: date | None, end: date | None) -> Request:
    return Request("GET", "/v1/schedule", {"from": start, "to": end}, list[ScheduleItem])


def lesson(lesson_id: int) -> Request:
    return Request("GET", f"/v1/lessons/{lesson_id}", model=Lesson)


def homework(start: date | None, end: date | None) -> Request:
    return Request("GET", "/v1/homework", {"from": start, "to": end}, list[Homework])


def homework_done(homework_id: int, done: bool) -> Request:
    return Request("POST" if done else "DELETE", f"/v1/homework/{homework_id}/done")


def exams() -> Request:
    return Request("GET", "/v1/exams", model=list[Exam])


def identity() -> Request:
    return Request("GET", "/v1/identity", model=Identity)


def notifications() -> Request:
    return Request("GET", "/v1/notifications", model=list[Notification])


def periods(start: date | None, end: date | None) -> Request:
    return Request("GET", "/v1/periods", {"from": start, "to": end}, list[PeriodDay])


def settings() -> Request:
    return Request("GET", "/v1/settings", model=Settings)


def update_settings(update: SettingsUpdate) -> Request:
    # Только переданные поля: «не передано» и null для сервиса разные вещи.
    body = update.model_dump(mode="json", exclude_unset=True)
    return Request("PATCH", "/v1/settings", body=body)


def update_contact(contact_id: int, value: str) -> Request:
    return Request("PUT", f"/v1/identity/contacts/{contact_id}", body={"value": value})


def subject(subject_id: int) -> Request:
    return Request("GET", f"/v1/subjects/{subject_id}", model=SubjectDetail)


def curriculum() -> Request:
    return Request("GET", "/v1/curriculum", model=Curriculum)


# Вход. Секреты (пароль, код, ответ на капчу) живут только в теле запроса.
def password_login(login: str, password: str) -> Request:
    body = {"login": login, "password": password}
    return Request("POST", "/v1/auth/password", model=TokenModel, body=body, login=True)


def esia_login(login: str, password: str) -> Request:
    body = {"login": login, "password": password}
    return Request("POST", "/v1/auth/esia", model=LoginResult, body=body, login=True)


def esia_code(flow_id: str, code: str) -> Request:
    path = f"/v1/auth/esia/{flow_id}/code"
    return Request("POST", path, model=LoginResult, body={"code": code}, login=True)


def esia_captcha(flow_id: str, answer: str) -> Request:
    path = f"/v1/auth/esia/{flow_id}/captcha"
    return Request("POST", path, model=LoginResult, body={"answer": answer}, login=True)


def esia_renew(flow_id: str) -> Request:
    return Request("POST", f"/v1/auth/esia/{flow_id}/captcha/renew", model=LoginStep, login=True)


def esia_cancel(flow_id: str) -> Request:
    return Request("DELETE", f"/v1/auth/esia/{flow_id}", login=True)


# --- родитель ---


def parent_me() -> Request:
    return Request("GET", "/v1/parent/me", model=ParentMe)


def parent_identity() -> Request:
    return Request("GET", "/v1/parent/identity", model=Identity)


def parent_avatar() -> Request:
    return Request("GET", "/v1/parent/avatar", model=Avatar)


def parent_children() -> Request:
    return Request("GET", "/v1/parent/children", model=list[Child])


def parent_settings() -> Request:
    return Request("GET", "/v1/parent/settings", model=Settings)


def parent_update_settings(update: SettingsUpdate) -> Request:
    body = update.model_dump(mode="json", exclude_unset=True)
    return Request("PATCH", "/v1/parent/settings", body=body)


def parent_update_contact(contact_id: int, value: str) -> Request:
    return Request("PUT", f"/v1/parent/identity/contacts/{contact_id}", body={"value": value})


def parent_journal_acks(child_id: int, start: date | None, end: date | None) -> Request:
    params = {"child_id": child_id, "from": start, "to": end}
    return Request("GET", "/v1/parent/journal-acks", params, list[JournalAck])


def parent_acknowledge_journal(child_id: int, week: date | None) -> Request:
    body: dict = {"child_id": child_id}
    if week is not None:
        body["week"] = week.isoformat()
    return Request("POST", "/v1/parent/journal-acks", body=body)
