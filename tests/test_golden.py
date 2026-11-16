"""Золотые снимки: публичные ответы шлюза и запросы, которые он шлёт дневнику.

Снимки не зависят от транспорта: у запроса записаны метод, URL без запроса,
параметры, заголовки (без Authorization, Cookie и User-Agent) и тело JSON.
Обновить эталон: UPDATE_GOLDEN=1 pytest tests/test_golden.py
"""

import copy
import json
import os
import typing
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
from pydantic import TypeAdapter

from diarysdk._gateway import DiaryGateway
from diarysdk.models.avatar import Avatar
from diarysdk.models.settings import SettingsThemeUpdate, SettingsUpdate
from tests.fakes import CTX, GUID, HOSTS, FakeTransport, Sent, add_diary_routes, fixture

GOLDEN = Path(__file__).parent / "golden"
TODAY = date(2026, 10, 24)
START = date(2026, 9, 1)
END = date(2026, 10, 24)
# Заголовки, которых в снимке нет: секреты и то, что выбирает сам транспорт.
HIDDEN_HEADERS = {"authorization", "cookie", "user-agent"}

Call = Callable[[DiaryGateway], Awaitable[object]]

READS: dict[str, Call] = {
    "me": lambda g: g.me(CTX),
    "school": lambda g: g.school(CTX),
    "avatar": lambda g: g.avatar(CTX),
    "exams": lambda g: g.exams(CTX),
    "final_marks": lambda g: g.final_marks(CTX, 2025),
    "homework": lambda g: g.homework(CTX, date(2026, 10, 24), date(2026, 10, 31)),
    "identity": lambda g: g.identity(CTX),
    "lesson": lambda g: g.lesson(CTX, 20001),
    "marks": lambda g: g.marks(CTX, START, END),
    "mark": lambda g: g.mark(CTX, 10001),
    "subjects": lambda g: g.subjects(CTX),
    "subject": lambda g: g.subject(CTX, 101),
    "rating": lambda g: g.rating(CTX, TODAY),
    "rating_subject": lambda g: g.rating(CTX, TODAY, 101),
    "rating_subjects": lambda g: g.rating_subjects(CTX, TODAY),
    "rating_history": lambda g: g.rating_history(CTX, START, END),
    "notifications": lambda g: g.notifications(CTX),
    "periods": lambda g: g.periods(CTX, START, date(2027, 8, 31)),
    "curriculum": lambda g: g.curriculum(CTX),
    "settings": lambda g: g.settings(CTX),
    "schedule": lambda g: g.schedule(CTX, date(2026, 10, 19), date(2026, 10, 25)),
}

SETTINGS_UPDATE = SettingsUpdate(
    goal=True, theme=SettingsThemeUpdate(color_pattern="pink"), schedule_type="full"
)
CARD = f"/api/persondata/v1/persons/{GUID}"
EMAIL = {
    "id": 2,
    "person_id": GUID,
    "type_id": 7,
    "type": {"id": 7, "name": "Электронная почта"},
    "data": "old@example.test",
    "default": False,
    "validation_state_id": 3,
    "validated_at": "2026-01-01",
}

WRITES: dict[str, Call] = {
    "set_homework_done": lambda g: g.set_homework_done(CTX, 555, True),
    "update_settings": lambda g: g.update_settings(CTX, SETTINGS_UPDATE),
    "update_contact": lambda g: g.update_contact(CTX, 2, "new.address@example.test"),
}


def _fake() -> FakeTransport:
    fake = FakeTransport()
    add_diary_routes(fake)
    # Аватарка — текст, чтобы её байты записывались в JSON.
    fake.add(f"/avatars/{GUID}", b"avatar-bytes", content_type="image/png")
    fake.add("/family/mobile/v1/notifications/search", fixture("notifications.json"))
    fake.add("/family/mobile/v1/periods_schedules", fixture("periods_schedules.json"))
    fake.add("/family/mobile/v1/programs/parallel_curriculum/1", fixture("curriculum.json"))
    fake.add("/family/mobile/v1/homeworks/555/done", b"")
    fake.add("GET /api/usersettings/v1", fixture("user_settings.json"))
    fake.add("PUT /api/usersettings/v1", b"")
    card = fixture("person_data.json")
    card["contacts"] = [*card["contacts"], copy.deepcopy(EMAIL)]
    fake.add(CARD, card)
    fake.add(f"PUT {CARD}/contacts/2", b"")
    return fake


def _request(sent: Sent) -> dict:
    url = urlsplit(sent.url)
    params = {**dict(parse_qsl(url.query)), **{k: str(v) for k, v in sent.params.items()}}
    headers = {k.lower(): v for k, v in sent.headers.items()}
    snapshot = {
        "method": sent.method,
        "url": f"{url.scheme}://{url.netloc}{url.path}",
        "params": dict(sorted(params.items())),
        "headers": {k: v for k, v in sorted(headers.items()) if k not in HIDDEN_HEADERS},
        "json": sent.json,
    }
    if "authorization" in headers:
        snapshot["auth"] = True
    return snapshot


async def _run(call: Call) -> tuple[object, list[dict]]:
    fake = _fake()
    result = await call(DiaryGateway(fake, HOSTS, today=lambda: TODAY))
    return result, [_request(sent) for sent in fake.sent]


def _output(name: str, result: object) -> object:
    if isinstance(result, Avatar):
        return {"content": result.content.decode(), "content_type": result.content_type}
    hints = typing.get_type_hints(getattr(DiaryGateway, name.removesuffix("_subject")))
    return TypeAdapter(hints["return"]).dump_python(result, mode="json")


def _check(name: str, data: object) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path = GOLDEN / f"{name}.json"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.write_text(text, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("name", READS)
async def test_read_output_matches_golden(name):
    result, _ = await _run(READS[name])

    _check(name, _output(name, result))


async def test_read_requests_match_golden():
    requests = {name: (await _run(call))[1] for name, call in READS.items()}

    _check("reads", requests)


async def test_write_requests_match_golden():
    requests = {name: (await _run(call))[1] for name, call in WRITES.items()}

    _check("writes", requests)
