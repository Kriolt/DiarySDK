"""Синхронные обёртки: тот же интерфейс, что у async-классов, в своём потоке."""

import faulthandler
import inspect
import json
import threading
from datetime import UTC, date, datetime

import httpx
import pytest
from httpx import ASGITransport

from diarysdk import Diary as AsyncDiary
from diarysdk import Student as AsyncStudent
from diarysdk import Token, errors, sync
from diarysdk import _protocols as protocols
from diarysdk._port import EsiaStep, MfaChallenge
from diarysdk.remote import RemoteDiary as AsyncRemoteDiary
from diarysdk.remote import RemoteStudent
from diarysdk.server.app import create_app
from diarysdk.server.keys import hash_key
from tests.conftest import API_KEY
from tests.fakes import HOSTS, STUDENT
from tests.remote.esia import FRESH, IMAGE, SMS, EsiaDiary, Session
from tests.test_client import READS, STUDENT_WRITES, DiaryServer
from tests.test_golden import GOLDEN, _output
from tests.tokens import make_token, valid_token


@pytest.fixture
def fixed_now(monkeypatch):
    """Токены из фикстур живут до 1 ноября 2026: «сейчас» — 24 октября."""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 24, 12, 0, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr("diarysdk.server.edge.auth.datetime", Frozen)
    monkeypatch.setattr("diarysdk.client._utcnow", lambda: Frozen.now(UTC))


@pytest.fixture(autouse=True)
def full_key(keys_file):
    keys_file.write_text(f"tests {hash_key(API_KEY)} login,write_profile\n")


@pytest.fixture
def token(fixed_now):
    return Token(make_token(STUDENT.expires_at, sub="1000001"))


def portal_threads():
    return [t for t in threading.enumerate() if t.name == "diarysdk-sync"]


@pytest.fixture(autouse=True)
def no_leaked_threads():
    yield
    assert portal_threads() == []


def direct_diary(server: DiaryServer | None = None, **options):
    server = server or DiaryServer()
    http = httpx.AsyncClient(transport=httpx.MockTransport(server))
    return sync.Diary(hosts=HOSTS, http=http, **options), server


def remote_diary(settings, server: DiaryServer | None = None, gateway=None):
    server = server or DiaryServer()
    inner = server.diary()
    if gateway is not None:
        inner._gateway = gateway
    app = create_app(settings, diary=inner)
    http = httpx.AsyncClient(transport=ASGITransport(app), base_url="http://t")
    return sync.RemoteDiary("http://t", API_KEY, http=http), server


@pytest.fixture(params=["direct", "remote"])
def make_diary(request, settings):
    """Синхронный дневник обоих видов; у обоих шлюз — подставной ЕСИА."""

    def make(gateway):
        if request.param == "direct":
            diary, _ = direct_diary()
            diary._target._gateway = gateway
            return diary
        return remote_diary(settings, gateway=gateway)[0]

    return make


# --- результаты ---


@pytest.mark.parametrize("name", READS)
def test_sync_student_matches_async(settings, token, name):
    call, golden = READS[name]
    expected = json.loads((GOLDEN / f"{golden}.json").read_text(encoding="utf-8"))
    results = []
    for build in (lambda: direct_diary()[0], lambda: remote_diary(settings)[0]):
        with build() as diary:
            # Лямбда из READS зовёт метод и возвращает его результат: у обёртки он готов сразу.
            results.append(call(diary.student(token)))

    assert results[0] == results[1]
    assert _output(golden, results[0]) == expected


@pytest.mark.parametrize("name", STUDENT_WRITES)
def test_sync_writes_send_the_same_requests(settings, token, name):
    wires = []
    for build in (lambda: direct_diary(), lambda: remote_diary(settings)):
        diary, server = build()
        with diary:
            assert STUDENT_WRITES[name](diary.student(token)) is None
        wires.append(
            [
                (r.method, r.url.path, r.content)
                for r in server.requests
                if "profile" not in r.url.path
            ]
        )

    assert wires[0] == wires[1]
    assert wires[0]


def test_errors_keep_their_class(settings, token):
    for diary in (direct_diary()[0], remote_diary(settings)[0]):
        with diary:
            with pytest.raises(errors.BadRequest):
                diary.student(token).marks(date(2020, 1, 1), date(2026, 1, 1))
            with pytest.raises(errors.TokenInvalid):
                diary.student("не токен").marks()


# --- вход ---


def esia_gateway(session=None, **answers):
    session = session or Session("captcha")
    base = {
        "esia_start": (session, EsiaStep(captcha=IMAGE)),
        "esia_captcha": EsiaStep(mfa=SMS),
        "esia_captcha_renew": EsiaStep(captcha=FRESH),
        "esia_code": valid_token(),
    }
    return EsiaDiary(**{**base, **answers}), session


def test_sync_login_flow(make_diary):
    gateway, _ = esia_gateway()
    with make_diary(gateway) as diary:
        flow = diary.login.esia("a", "b")
        assert isinstance(flow, sync.LoginFlow)
        assert (flow.kind, flow.mfa, flow.captcha.image) == ("captcha", None, IMAGE.image)

        assert flow.renew_captcha() is flow
        assert flow.captcha.image == FRESH.image
        assert flow.answer_captcha("ответ") is flow
        assert (flow.kind, flow.mfa.attempts_left, flow.captcha) == ("mfa", 3, None)

        token = flow.submit_code("246813")
    assert isinstance(token, Token)
    assert token.method == "esia"


def test_sync_bad_code_keeps_flow_usable(make_diary):
    bad = errors.BadCode(
        step=MfaChallenge(kind="sms", contact=None, ttl=300, attempts_left=2),
    )
    gateway, _ = esia_gateway(esia_code=bad)
    with make_diary(gateway) as diary:
        flow = diary.login.esia("a", "b")
        flow.answer_captcha("ответ")
        with pytest.raises(errors.BadCode) as caught:
            flow.submit_code("111111")

        assert caught.value.flow is flow
        assert flow.mfa.attempts_left == 2
        gateway.answers["esia_code"] = valid_token()
        assert isinstance(flow.submit_code("246813"), Token)


def test_sync_password_and_flow_close(make_diary):
    gateway, session = esia_gateway(password_login=valid_token())
    with make_diary(gateway) as diary:
        assert diary.login.password("a", "b").method == "password"
        flow = diary.login.esia("a", "b")
        assert flow.close() is None
        assert flow.close() is None
    assert session.closed >= 1


# --- цикл событий и поток ---


async def test_sync_inside_running_loop(settings, token):
    # Вызов блокирует цикл вызывающего, но не зависает: работа идёт в потоке портала.
    faulthandler.dump_traceback_later(20, exit=True)
    try:
        for diary in (direct_diary()[0], remote_diary(settings)[0]):
            with diary:
                assert diary.student(token).school().name
    finally:
        faulthandler.cancel_dump_traceback_later()


def test_close_stops_thread():
    diary, _ = direct_diary()
    assert len(portal_threads()) == 1

    diary.close()

    assert portal_threads() == []
    diary.close()  # повторно — не ошибка
    with pytest.raises(RuntimeError, match="закрыт"):
        diary.student(valid_token()).school()


def test_context_manager_closes_thread(settings):
    with remote_diary(settings)[0]:
        assert len(portal_threads()) == 1
    assert portal_threads() == []


def test_constructor_failure_leaves_no_thread():
    with pytest.raises(TypeError):
        sync.Diary(no_such_option=1)
    assert portal_threads() == []


def test_one_thread_per_instance(settings):
    first, _ = direct_diary()
    second, _ = remote_diary(settings)
    assert len(portal_threads()) == 2
    first.close()
    second.close()


def test_many_threads_share_one_student(token):
    # Контекст ученика запрашивается один раз, сколько бы потоков ни звало.
    diary, server = direct_diary()
    with diary:
        student = diary.student(token)
        threads = [threading.Thread(target=student.marks) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert server.count("GET", "/api/family/web/v1/profile") == 1


# --- сигнатуры ---


def _shape(function, *, annotations: bool):
    signature = inspect.signature(function)
    parameters = [
        (p.name, p.kind, p.default, p.annotation if annotations else None)
        for p in signature.parameters.values()
    ]
    return parameters, signature.return_annotation if annotations else None


def _methods(cls):
    return {
        name
        for name, _ in inspect.getmembers(cls, inspect.isfunction)
        if not name.startswith("_") or name in {"__enter__", "__exit__"}
    }


PAIRS = [
    (sync.Login, protocols.LoginLike),
    (sync.LoginFlow, protocols.LoginFlowLike),
    (sync.Student, protocols.StudentLike),
]


@pytest.mark.parametrize(("wrapper", "protocol"), PAIRS, ids=lambda x: x.__name__)
def test_sync_signatures(wrapper, protocol):
    methods = {
        name
        for name, _ in inspect.getmembers(protocol, inspect.isfunction)
        if not name.startswith("_")
    }
    assert methods
    assert _methods(wrapper) == methods
    for name in methods:
        proto = getattr(protocol, name)
        ours = getattr(wrapper, name)
        # Те же имена, виды, умолчания и аннотации; сама функция — обычная, не async.
        assert _shape(ours, annotations=True) == _shape(proto, annotations=True), name
        assert inspect.iscoroutinefunction(proto)
        assert not inspect.iscoroutinefunction(ours)


@pytest.mark.parametrize(
    ("wrapper", "async_class"), [(sync.Diary, AsyncDiary), (sync.RemoteDiary, AsyncRemoteDiary)]
)
def test_sync_diary_signatures(wrapper, async_class):
    assert _shape(wrapper.__init__, annotations=True) == _shape(
        async_class.__init__, annotations=True
    )
    assert _methods(wrapper) == {"student", "close", "__enter__", "__exit__"}
    assert _shape(wrapper.student, annotations=True) == _shape(
        protocols.DiaryLike.student, annotations=True
    )
    assert isinstance(inspect.getattr_static(wrapper, "login"), property)


@pytest.mark.parametrize("async_class", [AsyncStudent, RemoteStudent])
def test_sync_student_parameters_match_async(async_class):
    names = _methods(sync.Student)
    assert names == _methods(async_class)
    for name in names:
        assert _shape(getattr(sync.Student, name), annotations=False) == _shape(
            getattr(async_class, name), annotations=False
        ), name


# --- прерывание ожидания ---


def test_interrupt_while_waiting_cancels_the_portal_task(monkeypatch):
    import asyncio
    import concurrent.futures

    started = threading.Event()
    state = {}

    async def hang():
        state["task"] = asyncio.current_task()
        started.set()
        await asyncio.sleep(30)

    portal = sync._Portal()
    try:
        original = concurrent.futures.Future.result

        def interrupted(self, timeout=None):
            started.wait(5)
            raise KeyboardInterrupt

        monkeypatch.setattr(concurrent.futures.Future, "result", interrupted)
        with pytest.raises(KeyboardInterrupt):
            portal.run(hang())
        monkeypatch.setattr(concurrent.futures.Future, "result", original)

        deadline = threading.Event()
        for _ in range(100):
            if state["task"].cancelled() or state["task"].done():
                break
            deadline.wait(0.05)
        assert state["task"].cancelled()
    finally:
        portal.stop()


def test_sync_does_not_reexport_async_remote_classes():
    # Приватные псевдонимы: sync.RemoteStudent не должен подсовывать async-класс.
    for name in ("RemoteLogin", "RemoteLoginFlow", "RemoteStudent"):
        assert not hasattr(sync, name), name
