"""Один интерфейс у ядра и удалённого клиента: сигнатуры, результаты, ошибки."""

import asyncio
import inspect
import json
import re

import httpx
import pytest
from httpx import ASGITransport

from diarysdk import Diary, Login, LoginFlow, Student, errors
from diarysdk import _protocols as protocols
from diarysdk.remote import RemoteDiary, RemoteLogin, RemoteLoginFlow, RemoteStudent
from diarysdk.server.app import create_app
from diarysdk.server.keys import hash_key
from tests.conftest import API_KEY
from tests.fakes import FakeDiary, core_diary
from tests.test_client import READS, STUDENT_WRITES, DiaryServer
from tests.test_golden import GOLDEN, _output
from tests.tokens import valid_token

PAIRS = [
    (Diary, RemoteDiary, protocols.DiaryLike),
    (Login, RemoteLogin, protocols.LoginLike),
    (LoginFlow, RemoteLoginFlow, protocols.LoginFlowLike),
    (Student, RemoteStudent, protocols.StudentLike),
]
# Конструкторы у двойников разные: у удалённого есть адрес, ключ и свои настройки.
EXCLUDED = {"__init__"}


def _methods(cls) -> set[str]:
    return {
        name
        for name, _ in inspect.getmembers(cls, inspect.isfunction)
        if not name.startswith("_") or name in {"__aenter__", "__aexit__"}
    }


def _properties(cls) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(cls, lambda m: isinstance(m, property))
        if not name.startswith("_")
    }


def _shape(annotation) -> str:
    """Аннотация как строка; `RemoteX` приведён к `X` ядра."""
    return re.sub(r"diarysdk\.remote\.\w+\.Remote(\w+)", r"diarysdk.client.\1", str(annotation))


def _signature(function) -> tuple:
    signature = inspect.signature(function, eval_str=True)
    parameters = [
        (p.name, p.kind, p.default, _shape(p.annotation)) for p in signature.parameters.values()
    ]
    return parameters, _shape(signature.return_annotation)


def _parameters(function) -> list[tuple]:
    """Имя, вид и значение по умолчанию каждого параметра (аннотации — отдельно)."""
    # Без eval_str: имена аннотаций протоколов лежат под TYPE_CHECKING.
    signature = inspect.signature(function)
    return [(p.name, p.kind, p.default) for p in signature.parameters.values()]


@pytest.mark.parametrize(("core", "remote", "protocol"), PAIRS, ids=lambda x: x.__name__)
def test_signatures_match(core, remote, protocol):
    methods = _methods(protocol)
    assert methods, "протокол без методов: тест проверял бы пустоту"

    # Ни лишних открытых методов, ни пропавших: ни у ядра, ни у удалённого клиента.
    assert _methods(core) == methods
    assert _methods(remote) == methods
    # Свойства протокола, которых нет на классе, — атрибуты экземпляра (см. ниже).
    assert _properties(core) == _properties(remote) <= _properties(protocol)
    for name in sorted(methods):
        assert _signature(getattr(core, name)) == _signature(getattr(remote, name)), name
        # И с самим протоколом: имена, виды и значения по умолчанию параметров.
        expected = _parameters(getattr(protocol, name))
        assert _parameters(getattr(core, name)) == expected, name
        assert _parameters(getattr(remote, name)) == expected, name
    for name in sorted(_properties(core)):
        assert _signature(getattr(core, name).fget) == _signature(getattr(remote, name).fget), name


# --- результаты ---


@pytest.fixture(autouse=True)
def full_key(keys_file):
    """Ключ потребителя с обоими разрешениями: вход и правка контактов."""
    keys_file.write_text(f"tests {hash_key(API_KEY)} login,write_profile\n")


@pytest.fixture
def freeze_server_clock(monkeypatch):
    """Токены в фикстурах живут до 1 ноября 2026: «сейчас» для сервера — 24 октября."""
    import datetime as dt

    class Frozen(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime(2026, 10, 24, 12, 0, tzinfo=dt.UTC).astimezone(tz)

    monkeypatch.setattr("diarysdk.server.edge.auth.datetime", Frozen)
    monkeypatch.setattr("diarysdk.client._utcnow", lambda: Frozen.now(dt.UTC))


@pytest.fixture
def token():

    from diarysdk import Token
    from tests.fakes import STUDENT
    from tests.tokens import make_token

    return Token(make_token(STUDENT.expires_at, sub="1000001"))


class Both:
    """Ядро и удалённый клиент поверх одного и того же подставного дневника."""

    def __init__(self, settings, **options):
        self.direct_server = DiaryServer()
        self.remote_server = DiaryServer()
        self.direct = self.direct_server.diary(**options)
        app = create_app(settings, diary=self.remote_server.diary(**options))
        http = httpx.AsyncClient(transport=ASGITransport(app), base_url="http://t")
        self.remote = RemoteDiary("http://t", API_KEY, http=http)

    async def aclose(self):
        await self.direct.aclose()
        await self.remote.aclose()


@pytest.fixture
async def both(settings, freeze_server_clock):
    pair = Both(settings)
    try:
        yield pair
    finally:
        await pair.aclose()


def _wire(server: DiaryServer):
    return [
        (r.method, r.url.path, dict(r.url.params), r.content)
        for r in server.requests
        if "profile" not in r.url.path
    ]


@pytest.mark.parametrize("name", READS)
async def test_same_results(both, token, name):
    call, golden = READS[name]
    expected = json.loads((GOLDEN / f"{golden}.json").read_text(encoding="utf-8"))

    direct = await call(both.direct.student(token))
    remote = await call(both.remote.student(token))

    assert remote == direct
    assert _output(golden, remote) == expected
    assert _wire(both.remote_server) == _wire(both.direct_server)


@pytest.mark.parametrize("name", STUDENT_WRITES)
async def test_same_writes(both, token, name):
    await STUDENT_WRITES[name](both.direct.student(token))
    await STUDENT_WRITES[name](both.remote.student(token))

    assert _wire(both.remote_server) == _wire(both.direct_server)
    assert _wire(both.remote_server)


# --- ошибки ---


def _error_classes():
    found = []

    def walk(cls):
        found.append(cls)
        for sub in cls.__subclasses__():
            walk(sub)

    walk(errors.DiaryError)
    return [
        cls
        for cls in found
        if not cls.__name__.startswith("_")
        and cls.__module__ == errors.__name__  # внутренние подклассы ядро ловит само
        and not issubclass(cls, errors.RemoteError)
        and cls is not errors.WriteUncertain
    ]


def _make(cls):
    if cls is errors.UnsupportedStep:
        return cls(what="шаг")
    if issubclass(cls, errors.SettingError) and cls.__init__ is not errors.SettingError.__init__:
        return cls(field="goal")
    return cls()


@pytest.fixture
def instant_sleep(monkeypatch):
    async def fast(seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", fast)


@pytest.fixture
async def faulty(settings, instant_sleep):
    """Ядро и удалённый клиент поверх одного подставного дневника, который роняет вызовы."""
    fake = FakeDiary()
    app = create_app(settings, diary=core_diary(fake))
    http = httpx.AsyncClient(transport=ASGITransport(app), base_url="http://t")
    async with core_diary(fake) as direct, RemoteDiary("http://t", API_KEY, http=http) as remote:
        yield fake, direct, remote


@pytest.mark.parametrize("cls", _error_classes(), ids=lambda c: c.__name__)
async def test_same_errors(faulty, cls):
    fake, direct, remote = faulty
    fake.answers["school"] = _make(cls)
    token = valid_token()

    with pytest.raises(errors.DiaryError) as expected:
        await direct.student(token).school()
    with pytest.raises(errors.DiaryError) as caught:
        await remote.student(token).school()

    assert type(expected.value) is cls
    assert type(caught.value) is cls
    assert (caught.value.code, str(caught.value)) == (expected.value.code, str(expected.value))


@pytest.mark.parametrize(
    "cause", [errors.UpstreamTimeout(), errors.UpstreamError(upstream_status=502)]
)
async def test_remote_write_uncertain(faulty, cause):
    fake, direct, remote = faulty
    fake.answers["set_homework_done"] = errors.WriteUncertain(cause=cause)
    token = valid_token()

    with pytest.raises(errors.WriteUncertain) as expected:
        await direct.student(token).homework_done(1)
    with pytest.raises(errors.WriteUncertain) as caught:
        await remote.student(token).homework_done(1)

    assert type(caught.value.cause) is type(expected.value.cause) is type(cause)
    assert caught.value.code == expected.value.code
    assert caught.value.upstream_status == expected.value.upstream_status
    # Запись не повторяется: дневник получил её один раз.
    assert fake.calls.count("set_homework_done") == 2


async def test_core_own_errors_reach_remote_with_same_class(both):
    # Ошибки самого ядра (не подставленные): просроченный токен, мусор, длинный период.
    from datetime import UTC, date, datetime

    from tests.tokens import make_token

    expired = make_token(datetime(2026, 10, 1, tzinfo=UTC), sub="1000001")
    cases = [
        (expired, lambda s: s.marks(), errors.TokenExpired),
        ("не токен", lambda s: s.marks(), errors.TokenInvalid),
        (valid_token(), lambda s: s.marks(date(2020, 1, 1), date(2026, 1, 1)), errors.BadRequest),
    ]
    for token, call, cls in cases:
        with pytest.raises(cls):
            await call(both.direct.student(token))
        with pytest.raises(cls):
            await call(both.remote.student(token))


@pytest.mark.parametrize("value", ["не почта", "a@b@c", "ab", "x@y z", "@d.test", "a@" + "d" * 260])
async def test_update_contact_validates_email_in_core_like_server(both, value):
    token = valid_token()

    with pytest.raises(errors.BadRequest) as expected:
        await both.direct.student(token).update_contact(2, value)
    with pytest.raises(errors.BadRequest) as caught:
        await both.remote.student(token).update_contact(2, value)

    assert str(caught.value) == str(expected.value)
    # До записи в дневник дело не дошло ни в ядре, ни на сервере.
    for served in (both.direct_server, both.remote_server):
        assert [r for r in served.requests if r.method == "PUT"] == []


async def test_definite_upstream_error_on_write_is_not_write_uncertain_in_remote(faulty):
    fake, direct, remote = faulty
    fake.answers["set_homework_done"] = errors.UpstreamError(upstream_status=500)
    token = valid_token()

    with pytest.raises(errors.UpstreamError) as expected:
        await direct.student(token).homework_done(1)
    with pytest.raises(errors.UpstreamError) as caught:
        await remote.student(token).homework_done(1)

    assert not isinstance(expected.value, errors.WriteUncertain)
    assert type(caught.value) is errors.UpstreamError
    assert caught.value.upstream_status == expected.value.upstream_status == 500
