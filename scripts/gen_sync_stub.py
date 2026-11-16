"""Собирает `diarysdk/sync.pyi` по протоколам: `python scripts/gen_sync_stub.py`.

Обёртки в `diarysdk/sync.py` строятся во время работы, поэтому типы для
проверяющих и IDE лежат в заглушке; тест сверяет её с этим выводом.
"""

import inspect
import re
import typing
from pathlib import Path

from diarysdk import _protocols as protocols
from diarysdk.client import Diary
from diarysdk.remote import RemoteDiary

TARGET = Path(__file__).resolve().parent.parent / "diarysdk" / "sync.pyi"
RENAMES = {"LoginFlowLike": "LoginFlow", "LoginLike": "Login", "StudentLike": "Student"}
HEADER = '''\
"""Заглушка типов для `sync.py`; собрана `scripts/gen_sync_stub.py`, руками не правится."""

from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Literal, Self

import httpx

from diarysdk import Avatar, Hosts
from diarysdk.models.auth import Captcha, LoginMfa
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
from diarysdk.token import Token
'''


def _name(text: str) -> str:
    return re.sub(r"\b(LoginFlowLike|LoginLike|StudentLike)\b", lambda m: RENAMES[m[0]], text)


def _annotation(value: object) -> str:
    return _name(value if isinstance(value, str) else getattr(value, "__name__", str(value)))


def _params(function: typing.Callable) -> str:
    parts, star = [], False
    for parameter in inspect.signature(function).parameters.values():
        text = parameter.name
        if parameter.name == "self":
            parts.append(text)
            continue
        if parameter.kind is parameter.KEYWORD_ONLY and not star:
            parts.append("*")
            star = True
        if parameter.annotation is not parameter.empty:
            text += f": {_annotation(parameter.annotation)}"
        if parameter.default is not parameter.empty:
            text += f" = {parameter.default!r}"
        parts.append(text)
    return ", ".join(parts)


def _returns(function: typing.Callable) -> str:
    annotation = inspect.signature(function).return_annotation
    return _annotation(annotation)


def _method(name: str, function: typing.Callable) -> str:
    return f"    def {name}({_params(function)}) -> {_returns(function)}: ..."


def _members(protocol: type, skip: set[str] = frozenset()) -> list[str]:
    lines = []
    for name in sorted(typing.get_protocol_members(protocol)):
        if name in skip or name.startswith("_"):
            continue
        raw = inspect.getattr_static(protocol, name)
        if isinstance(raw, property):
            lines.append("    @property")
            lines.append(f"    def {name}(self) -> {_returns(raw.fget)}: ...")
        else:
            lines.append(_method(name, raw))
    return lines


def _plain(protocol: type) -> str:
    return "\n".join(_members(protocol))


def _entry(name: str, async_class: type) -> str:
    skip = {"aclose"}
    body = [
        f"    def __init__({_params(async_class.__init__)}) -> None: ...",
        *_members(protocols.DiaryLike, skip),
        "    def close(self) -> None: ...",
        "    def __enter__(self) -> Self: ...",
        "    def __exit__(self, *exc: object) -> None: ...",
    ]
    return f"class {name}:\n" + "\n".join(body)


def render() -> str:
    blocks = [
        HEADER,
        f"class Login:\n{_plain(protocols.LoginLike)}",
        f"class LoginFlow:\n{_plain(protocols.LoginFlowLike)}",
        f"class Student:\n{_plain(protocols.StudentLike)}",
        _entry("Diary", Diary),
        _entry("RemoteDiary", RemoteDiary),
    ]
    # В заглушке между классами одна пустая строка, как требует ruff для .pyi.
    return "\n".join(block.rstrip("\n") + "\n" for block in blocks)


if __name__ == "__main__":
    TARGET.write_text(render(), encoding="utf-8")
