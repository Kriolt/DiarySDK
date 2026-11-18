"""Живая проверка на подставном дневнике: чтения — да, записи — нет, значений полей в выводе нет."""

import importlib.util
import inspect
import io
from pathlib import Path

import httpx
import pytest

from diarysdk import BadCredentials, Diary
from diarysdk import client as client_module
from tests.fakes import HOSTS, fixture
from tests.test_client import DiaryServer, now  # noqa: F401 - now: фикстура срока токена
from tests.tokens import valid_token

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "live_check.py"
spec = importlib.util.spec_from_file_location("live_check", SCRIPT)
live_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live_check)

# Значения из фикстур: в вывод проверки попадать не должны.
FIXTURE_VALUES = ["Гимназия", "Петровна", "avatar-bytes", "Тестов", "Классная"]
SECRET = "секрет-токен-для-проверки"


def _no_input(prompt: str) -> str:
    raise AssertionError(f"неожиданный запрос ввода: {prompt}")


async def _run(server, method="token", env=None, ask=_no_input, ask_secret=_no_input):
    out = io.StringIO()
    http = httpx.AsyncClient(transport=httpx.MockTransport(server))
    code = await live_check.run(
        method, env or {}, ask, ask_secret, out, diary=Diary(hosts=HOSTS, http=http)
    )
    return code, out.getvalue()


async def test_reads_ok_and_no_field_values(now):  # noqa: F811
    server = DiaryServer()

    code, output = await _run(server, env={"DIARYSDK_TOKEN": valid_token()})

    assert code == 0
    # Справки ученику недоступны: дневник отдаёт их только родителю.
    expected = {f"ok {name}" for name in _read_names() - {"certificates"}}
    assert set(output.splitlines()) == expected | {"skip certificates: недоступно для этой роли"}
    for value in FIXTURE_VALUES:
        assert value not in output


async def test_no_write_request_is_sent(now):  # noqa: F811
    server = DiaryServer()

    await _run(server, env={"DIARYSDK_TOKEN": valid_token()})

    assert {r.method for r in server.requests} <= {"GET", "POST"}
    assert not [r for r in server.requests if r.url.path.endswith("/done")]


def _read_names() -> set[str]:
    public = {
        name
        for name, _ in inspect.getmembers(client_module.Student, inspect.iscoroutinefunction)
        if not name.startswith("_")
    }
    return public - live_check.WRITES


async def test_failure_prints_class_and_paths_only(now):  # noqa: F811
    server = DiaryServer()
    server.fake.add("/family/mobile/v1/school_info", {"name": 42, "secret": "Гимназия"})

    code, output = await _run(server, env={"DIARYSDK_TOKEN": valid_token()})

    assert code == 1
    failed = [line for line in output.splitlines() if line.startswith("fail ")]
    assert len(failed) == 1
    assert failed[0].startswith("fail school: UpstreamFormat")
    for value in FIXTURE_VALUES:
        assert value not in output


async def test_token_is_asked_with_secret_prompt_when_env_is_empty(now):  # noqa: F811
    prompts = []

    def ask_secret(prompt: str) -> str:
        prompts.append(prompt)
        return valid_token()

    code, output = await _run(DiaryServer(), ask_secret=ask_secret)

    assert code == 0
    assert len(prompts) == 1
    assert "ok me" in output


async def test_password_login_failure_is_reported_without_secrets(monkeypatch):
    async def refuse(self, login, password):
        raise BadCredentials()

    monkeypatch.setattr(type(Diary().login), "password", refuse)

    code, output = await _run(
        DiaryServer(),
        method="password",
        env={"DIARYSDK_LOGIN": "user-login-1", "DIARYSDK_PASSWORD": SECRET},
    )

    assert code == 1
    assert output == "fail вход: BadCredentials\n"


def test_secrets_are_not_accepted_in_argv():
    for flag in ("--password", "--token", "--esia"):
        with pytest.raises(SystemExit):
            live_check.main([flag, SECRET])
    with pytest.raises(SystemExit):
        live_check.main([])


def test_script_neither_writes_files_nor_calls_student_writes():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "open(" not in source
    assert ".write_" not in source
    for name in live_check.WRITES:
        assert f".{name}" not in source


async def test_any_exception_is_reported_by_class_only(monkeypatch, now):  # noqa: F811
    async def broken_login(self, login, password):
        raise ValueError(SECRET)

    monkeypatch.setattr(type(Diary().login), "password", broken_login)
    code, output = await _run(
        DiaryServer(), method="password", env={"DIARYSDK_LOGIN": "l", "DIARYSDK_PASSWORD": "p"}
    )
    assert (code, output) == (1, "fail вход: ValueError\n")

    async def broken_read(self):
        raise KeyError(SECRET)

    monkeypatch.setattr(client_module.Student, "me", broken_read)
    code, output = await _run(DiaryServer(), env={"DIARYSDK_TOKEN": valid_token()})
    assert code == 1
    assert "fail me: KeyError\n" in output
    assert SECRET not in output


def test_skip_reason_tells_empty_list_from_missing_ids():
    def pick(item):
        return item

    assert live_check._first_id(None, pick) == "чтение не удалось"
    assert live_check._first_id([], pick) == "список пуст"
    assert live_check._first_id([None, None], pick) == "ни у одного элемента нет id"
    assert live_check._first_id([None, 7, 8], pick) == 7


async def test_parent_mode_checks_parent_and_every_child_without_values(now):  # noqa: F811
    from tests.test_parent import PARENT_GUID, parent_profile

    server = DiaryServer()
    server.fake.add("/api/family/web/v1/profile", parent_profile())
    server.fake.add(f"/api/persondata/v1/persons/{PARENT_GUID}", fixture("person_data.json"))
    server.fake.add(f"/api/avatarmanagement/v1/{PARENT_GUID}", [])
    server.fake.add("/api/ej/core/family/v1/aware_journals", [])

    code, output = await _run(server, method="parent", env={"DIARYSDK_TOKEN": valid_token()})

    lines = set(output.splitlines())
    assert {
        "ok parent.me",
        "ok parent.children",
        "ok parent.identity",
        "ok parent.settings",
    } <= lines
    assert "ok parent.journal_acks" in lines
    assert "skip parent.avatar: нет аватарки" in lines
    for child in ("child1", "child2"):
        assert f"ok {child}:marks" in lines
        assert f"ok {child}:certificates" in lines
        assert f"skip {child}:exams: недоступно для этой роли" in lines
    assert not [r for r in server.requests if r.method in ("POST", "PUT", "PATCH", "DELETE")]
    for value in [*FIXTURE_VALUES, "Пётр", PARENT_GUID]:
        assert value not in output
    assert code == 0


def test_parent_writes_are_listed_and_never_called():
    assert {"acknowledge_journal", "update_settings", "update_contact"} <= live_check.WRITES
    source = SCRIPT.read_text(encoding="utf-8")
    assert ".acknowledge_journal" not in source
