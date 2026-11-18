"""Публичный API ядра: Diary, Student, LoginFlow на подставном HTTP-дневнике."""

import asyncio
import inspect
import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from diarysdk import Diary, Token, errors
from diarysdk import _clock as clock
from diarysdk import _protocols as protocols
from diarysdk import client as client_module
from diarysdk._port import EsiaStep
from tests.fakes import HOSTS, STUDENT, FakeTransport
from tests.remote.esia import FRESH, IMAGE, SMS, Session
from tests.test_golden import GOLDEN, SETTINGS_UPDATE, TODAY, WRITES, _fake, _output
from tests.tokens import make_token, valid_token

SECRET_PASSWORD = "пароль-секрет-123"
SECRET_CODE = "424242"


class DiaryServer:
    """Подставной дневник поверх MockTransport: ответы из FakeTransport, журнал запросов."""

    def __init__(self, fake: FakeTransport | None = None) -> None:
        self.fake = fake or _fake()
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        keys = (f"{request.method} {request.url.path}", request.url.path)
        route = next((self.fake.routes[key] for key in keys if key in self.fake.routes), None)
        if route is None:
            raise AssertionError(f"подставной дневник не знает путь {request.url.path}")
        if isinstance(route, Exception):
            raise route
        headers = {"Content-Type": route.content_type or ""}
        return httpx.Response(route.status, content=route.body, headers=headers)

    def count(self, method: str, path: str) -> int:
        return sum(1 for r in self.requests if r.method == method and r.url.path == path)

    def diary(self, **options) -> Diary:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self))
        return Diary(hosts=HOSTS, http=http, **options)


@pytest.fixture
def server():
    return DiaryServer()


@pytest.fixture
def now(monkeypatch):
    """«Сейчас» для проверки срока токена: до истечения токена из фикстур."""
    moment = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(client_module, "_utcnow", lambda: moment)
    return moment


@pytest.fixture
async def diary(server, now):
    async with server.diary() as opened:
        yield opened


@pytest.fixture
def token():
    return Token(make_token(STUDENT.expires_at))


# --- чтения и записи ---


READS = {
    "me": (lambda s: s.me(), "me"),
    "school": (lambda s: s.school(), "school"),
    "avatar": (lambda s: s.avatar(), "avatar"),
    "exams": (lambda s: s.exams(), "exams"),
    "final_marks": (lambda s: s.final_marks(2025), "final_marks"),
    "homework": (lambda s: s.homework(date(2026, 10, 24), date(2026, 10, 31)), "homework"),
    "identity": (lambda s: s.identity(), "identity"),
    "lesson": (lambda s: s.lesson(20001), "lesson"),
    "marks": (lambda s: s.marks(date(2026, 9, 1), date(2026, 10, 24)), "marks"),
    "mark": (lambda s: s.mark(10001), "mark"),
    "subjects": (lambda s: s.subjects(), "subjects"),
    "subject": (lambda s: s.subject(101), "subject"),
    "rating": (lambda s: s.rating(TODAY), "rating"),
    "rating_subject": (lambda s: s.rating(TODAY, 101), "rating_subject"),
    "rating_subjects": (lambda s: s.rating_subjects(TODAY), "rating_subjects"),
    "rating_history": (
        lambda s: s.rating_history(date(2026, 9, 1), date(2026, 10, 24)),
        "rating_history",
    ),
    "notifications": (lambda s: s.notifications(), "notifications"),
    "periods": (lambda s: s.periods(date(2026, 9, 1), date(2027, 8, 31)), "periods"),
    "curriculum": (lambda s: s.curriculum(), "curriculum"),
    "school_teachers": (lambda s: s.school_teachers(), "school_teachers"),
    "academic_debts": (lambda s: s.academic_debts(2025), "academic_debts"),
    "work_program": (lambda s: s.work_program(5001), "work_program"),
    "subject_topics": (lambda s: s.subject_topics(101), "subject_topics"),
    "final_marks_file": (lambda s: s.final_marks_file(2025), "final_marks_file"),
    "control_works": (
        lambda s: s.control_works(date(2026, 9, 1), date(2027, 8, 31)),
        "control_works",
    ),
    "settings": (lambda s: s.settings(), "settings"),
    "schedule": (lambda s: s.schedule(date(2026, 10, 19), date(2026, 10, 25)), "schedule"),
}
# Записи: у них нет ответа, сверяется запрос.
STUDENT_WRITES = {
    "homework_done": lambda s: s.homework_done(555),
    "homework_undone": lambda s: s.homework_undone(555),
    "update_settings": lambda s: s.update_settings(SETTINGS_UPDATE),
    "update_contact": lambda s: s.update_contact(2, "new.address@example.test"),
}


@pytest.mark.parametrize("name", READS)
async def test_student_methods_match_golden(diary, token, name):
    call, golden = READS[name]

    result = await call(diary.student(token))

    expected = json.loads((GOLDEN / f"{golden}.json").read_text(encoding="utf-8"))
    assert _output(golden, result) == expected


def test_student_method_tests_cover_the_whole_surface():
    public = {
        name
        for name, member in inspect.getmembers(client_module.Student, inspect.iscoroutinefunction)
        if not name.startswith("_")
    }
    exercised = set()
    calls = [*READS.values(), *((c, None) for c in STUDENT_WRITES.values())]
    # Справки — только через родителя: их чтение проверяет tests/test_parity.py.
    calls.append((lambda s: s.certificates(), None))
    for call, _ in calls:
        probe = _Probe()
        call(probe)
        exercised.add(probe.name)
    assert public == exercised


class _Probe:
    """Ловит имя вызванного метода Student."""

    name = ""

    def __getattr__(self, name):
        self.name = name
        return lambda *args, **kwargs: None


@pytest.mark.parametrize("name", STUDENT_WRITES)
async def test_student_writes_send_golden_requests(diary, server, token, name):
    await STUDENT_WRITES[name](diary.student(token))

    wire = {
        "homework_done": [("POST", "/family/mobile/v1/homeworks/555/done")],
        "homework_undone": [("DELETE", "/family/mobile/v1/homeworks/555/done")],
        "update_settings": [("GET", "/api/usersettings/v1"), ("PUT", "/api/usersettings/v1")],
        "update_contact": [
            ("GET", f"/api/persondata/v1/persons/{STUDENT.person_guid}"),
            ("PUT", f"/api/persondata/v1/persons/{STUDENT.person_guid}/contacts/2"),
        ],
    }[name]
    sent = [(r.method, r.url.path) for r in server.requests if "profile" not in r.url.path]
    assert sent == wire


def test_writes_cover_the_gateway_writes():
    assert set(WRITES) == {"set_homework_done", "update_settings", "update_contact"}


async def test_default_periods_moscow(diary, server, token, monkeypatch):
    # 22:30 UTC в субботу — уже воскресенье 25 октября по Москве.
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 24, 22, 30, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(clock, "datetime", Frozen)
    student = diary.student(token)

    await student.marks()
    await student.homework()
    await student.schedule()

    marks, homework = (
        next(r for r in server.requests if r.url.path.endswith(path))
        for path in ("/marks", "/homeworks")
    )
    assert (marks.url.params["from"], marks.url.params["to"]) == ("2026-09-01", "2026-10-25")
    assert (homework.url.params["from"], homework.url.params["to"]) == ("2026-10-25", "2026-11-01")
    events = next(r for r in server.requests if r.url.path.endswith("/events"))
    assert (events.url.params["begin_date"], events.url.params["end_date"]) == (
        "2026-10-19",
        "2026-10-25",
    )


async def test_period_longer_than_limit_is_bad_request_without_requests(diary, server, token):
    with pytest.raises(errors.BadRequest):
        await diary.student(token).marks(date(2020, 1, 1), date(2026, 1, 1))

    assert server.requests == []


async def test_context_fetched_once_under_concurrency(diary, server, token):
    student = diary.student(token)

    await asyncio.gather(*(student.marks() for _ in range(20)))

    assert server.count("GET", "/api/family/web/v1/profile") == 1
    assert server.count("GET", "/family/mobile/v1/marks") == 20


async def test_context_is_shared_between_students_with_same_token(diary, server, token):
    await asyncio.gather(diary.student(token).marks(), diary.student(token.value).marks())

    assert server.count("GET", "/api/family/web/v1/profile") == 1


async def test_rejected_token_drops_cached_context(diary, server, token):
    student = diary.student(token)
    await student.marks()
    server.fake.add("/family/mobile/v1/marks", b"", status=401)
    with pytest.raises(errors.TokenInvalid):
        await student.marks()
    server.fake.add("/family/mobile/v1/marks", {"payload": []})

    await student.marks()

    assert server.count("GET", "/api/family/web/v1/profile") == 2


async def test_expired_token_is_rejected_without_requests(diary, server):
    expired = Token(make_token(datetime(2026, 10, 1, tzinfo=UTC)))

    with pytest.raises(errors.TokenExpired):
        await diary.student(expired).marks()

    assert server.requests == []


async def test_garbage_token_is_invalid_without_requests(diary, server):
    with pytest.raises(errors.TokenInvalid):
        await diary.student("не токен").marks()

    assert server.requests == []


async def test_multiple_children_error(diary, server, token):
    profile = json.loads(server.fake.routes["/api/family/web/v1/profile"].body)
    profile["children"] = [profile["children"][0], profile["children"][0]]
    server.fake.add("/api/family/web/v1/profile", profile)

    with pytest.raises(errors.MultipleChildren):
        await diary.student(token).me()


async def test_deadline_is_upstream_timeout(server, now, token):
    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=[])

    http = httpx.AsyncClient(transport=httpx.MockTransport(slow))
    async with Diary(hosts=HOSTS, http=http, deadline=0.05) as diary:
        with pytest.raises(errors.UpstreamTimeout):
            await diary.student(token).marks()


async def test_closed_diary_refuses_requests(server, now, token):
    diary = server.diary()
    await diary.aclose()

    with pytest.raises(RuntimeError):
        await diary.student(token).marks()
    assert server.requests == []


# --- записи без повтора ---


WRITE_CASES = {
    "homework_done": (
        lambda s: s.homework_done(555),
        "POST",
        "/family/mobile/v1/homeworks/555/done",
    ),
    "update_settings": (
        lambda s: s.update_settings(SETTINGS_UPDATE),
        "PUT",
        "/api/usersettings/v1",
    ),
    "update_contact": (
        lambda s: s.update_contact(2, "new.address@example.test"),
        "PUT",
        f"/api/persondata/v1/persons/{STUDENT.person_guid}/contacts/2",
    ),
}


@pytest.mark.parametrize("case", WRITE_CASES)
async def test_write_network_error_is_uncertain_no_retry(diary, server, token, case):
    call, method, path = WRITE_CASES[case]
    server.fake.fail(f"{method} {path}", httpx.ConnectError("обрыв"))

    with pytest.raises(errors.WriteUncertain) as caught:
        await call(diary.student(token))

    assert isinstance(caught.value.cause, errors.UpstreamError)
    assert server.count(method, path) == 1


@pytest.mark.parametrize("status", [502, 504])
@pytest.mark.parametrize("case", WRITE_CASES)
async def test_write_bad_gateway_is_uncertain_no_retry(diary, server, token, case, status):
    call, method, path = WRITE_CASES[case]
    server.fake.add(f"{method} {path}", b"", status=status)

    with pytest.raises(errors.WriteUncertain) as caught:
        await call(diary.student(token))

    assert caught.value.upstream_status == status
    assert server.count(method, path) == 1


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("case", ["homework_done"])
async def test_write_auth_refusal_is_plain_auth_error(diary, server, token, case, status):
    call, method, path = WRITE_CASES[case]
    server.fake.add(f"{method} {path}", b"", status=status)

    with pytest.raises(errors.TokenInvalid):
        await call(diary.student(token))


async def test_write_other_failure_is_plain_upstream_error(diary, server, token):
    call, method, path = WRITE_CASES["homework_done"]
    server.fake.add(f"{method} {path}", b"", status=500)

    with pytest.raises(errors.UpstreamError) as caught:
        await call(diary.student(token))

    assert not isinstance(caught.value, errors.WriteUncertain)


async def test_read_of_write_flow_failing_is_not_uncertain(diary, server, token):
    server.fake.fail("GET /api/usersettings/v1", httpx.ConnectError("обрыв"))

    with pytest.raises(errors.UpstreamError) as caught:
        await diary.student(token).update_settings(SETTINGS_UPDATE)

    assert not isinstance(caught.value, errors.WriteUncertain)
    assert server.count("PUT", "/api/usersettings/v1") == 0


# --- вход ---


class ScriptedGateway:
    """Дневник входа: заранее заданные ответы по очереди."""

    def __init__(self, start, code=(), captcha=(), renew=()):
        self.start = start
        self.code = list(code)
        self.captcha = list(captcha)
        self.renew = list(renew)
        self.calls: list[str] = []

    async def password_login(self, login, password):
        self.calls.append("password_login")
        return valid_token()

    async def esia_start(self, login, password):
        self.calls.append("esia_start")
        return self.start

    async def esia_code(self, session, code):
        return self._next("esia_code", self.code)

    async def esia_captcha(self, session, answer):
        return self._next("esia_captcha", self.captcha)

    async def esia_captcha_renew(self, session):
        return self._next("esia_captcha_renew", self.renew)

    def _next(self, name, queue):
        self.calls.append(name)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


async def test_password_login_gives_token(server):
    async with server.diary() as diary:
        diary._gateway = ScriptedGateway(None)

        token = await diary.login.password("login", SECRET_PASSWORD)

    assert isinstance(token, Token)
    assert token.method == "password"
    assert token.expires_at is not None


async def test_esia_without_steps_gives_token(server):
    async with server.diary() as diary:
        diary._gateway = ScriptedGateway((Session(None), valid_token()))

        token = await diary.login.esia("login", SECRET_PASSWORD)

    assert isinstance(token, Token)
    assert token.method == "esia"


async def test_esia_flow_mfa_then_token(server):
    session = Session("mfa")
    jwt = valid_token()
    gateway = ScriptedGateway((session, EsiaStep(mfa=SMS)), code=[jwt])
    async with server.diary() as diary:
        diary._gateway = gateway

        flow = await diary.login.esia("login", SECRET_PASSWORD)
        assert flow.kind == "mfa"
        assert flow.mfa.kind == "sms"
        assert flow.mfa.attempts_left == 3
        assert flow.captcha is None
        assert flow.expires_at > datetime.now(UTC)
        token = await flow.submit_code(SECRET_CODE)

    assert token.value == jwt
    assert token.method == "esia"
    assert session.closed >= 1


async def test_wrong_code_updates_same_flow_and_allows_retry(server):
    session = Session("mfa")
    fewer = SMS.__class__(kind="sms", contact=SMS.contact, ttl=300, attempts_left=2)
    gateway = ScriptedGateway(
        (session, EsiaStep(mfa=SMS)),
        code=[errors.BadCode(step=fewer), valid_token()],
    )
    async with server.diary() as diary:
        diary._gateway = gateway
        flow = await diary.login.esia("login", SECRET_PASSWORD)

        with pytest.raises(errors.BadCode) as caught:
            await flow.submit_code("000000")
        assert flow.mfa.attempts_left == 2
        assert caught.value.step.attempts_left == 2
        assert caught.value.flow is flow
        token = await flow.submit_code(SECRET_CODE)

    assert isinstance(token, Token)


async def test_captcha_then_mfa_updates_flow(server):
    session = Session("captcha")
    gateway = ScriptedGateway(
        (session, EsiaStep(captcha=IMAGE)),
        captcha=[errors.BadCaptcha(step=FRESH), EsiaStep(mfa=SMS)],
        renew=[EsiaStep(captcha=IMAGE)],
    )

    async with server.diary() as diary:
        diary._gateway = gateway
        flow = await diary.login.esia("login", SECRET_PASSWORD)
        assert flow.kind == "captcha"
        assert flow.captcha.image == IMAGE.image
        with pytest.raises(errors.BadCaptcha):
            await flow.answer_captcha("неверно")
        assert flow.captcha.image == FRESH.image
        assert await flow.renew_captcha() is flow
        assert flow.captcha.image == IMAGE.image
        session.waiting = "captcha"
        result = await flow.answer_captcha("верно")
        session.waiting = "mfa"

    assert result is flow
    assert flow.kind == "mfa"
    assert flow.mfa is not None
    assert flow.captcha is None


async def test_wrong_step_is_bad_request(server):
    async with server.diary() as diary:
        diary._gateway = ScriptedGateway((Session("mfa"), EsiaStep(mfa=SMS)))
        flow = await diary.login.esia("login", SECRET_PASSWORD)

        with pytest.raises(errors.BadRequest):
            await flow.answer_captcha("ответ")
        assert diary._gateway.calls == ["esia_start"]


async def test_failed_step_closes_flow(server):
    session = Session("mfa")
    gateway = ScriptedGateway((session, EsiaStep(mfa=SMS)), code=[errors.LoginBlocked()])
    async with server.diary() as diary:
        diary._gateway = gateway
        flow = await diary.login.esia("login", SECRET_PASSWORD)

        with pytest.raises(errors.LoginBlocked):
            await flow.submit_code(SECRET_CODE)
        with pytest.raises(errors.FlowExpired):
            await flow.submit_code(SECRET_CODE)

    assert session.closed >= 1


async def test_closed_flow_and_expired_flow(server, monkeypatch):
    session = Session("mfa")
    async with server.diary() as diary:
        diary._gateway = ScriptedGateway((session, EsiaStep(mfa=SMS)))
        flow = await diary.login.esia("login", SECRET_PASSWORD)
        flow.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        with pytest.raises(errors.FlowExpired):
            await flow.submit_code(SECRET_CODE)
        await flow.close()
        await flow.close()


async def test_diary_close_closes_open_flows(server):
    session = Session("mfa")
    async with server.diary() as diary:
        diary._gateway = ScriptedGateway((session, EsiaStep(mfa=SMS)))
        flow = await diary.login.esia("login", SECRET_PASSWORD)

    assert session.closed == 1
    with pytest.raises(errors.FlowExpired):
        await flow.submit_code(SECRET_CODE)


# --- секреты ---


async def test_repr_has_no_secrets(server, token):
    jwt = token.value
    session = Session("mfa")
    gateway = ScriptedGateway(
        (session, EsiaStep(mfa=SMS)), code=[errors.BadCode(step=SMS), valid_token()]
    )
    async with server.diary() as diary:
        diary._gateway = gateway
        student = diary.student(jwt)
        flow = await diary.login.esia("login-секрет", SECRET_PASSWORD)
        with pytest.raises(errors.BadCode) as caught:
            await flow.submit_code(SECRET_CODE)

        shown = [
            repr(token),
            str(token),
            repr(diary),
            str(diary),
            repr(diary.login),
            repr(student),
            str(student),
            repr(flow),
            str(flow),
            repr(caught.value),
            str(caught.value),
            repr(caught.value.step),
            *(str(arg) for arg in caught.value.args),
        ]

    text = "\n".join(shown)
    for secret in (
        jwt,
        jwt.split(".")[1],
        SECRET_PASSWORD,
        SECRET_CODE,
        "login-секрет",
        SMS.contact,
    ):
        assert secret not in text


async def test_password_error_text_has_no_secrets(server):
    class Refusing(ScriptedGateway):
        async def password_login(self, login, password):
            raise errors.BadCredentials()

    async with server.diary() as diary:
        diary._gateway = Refusing(None)
        with pytest.raises(errors.BadCredentials) as caught:
            await diary.login.password("login-секрет", SECRET_PASSWORD)

    assert SECRET_PASSWORD not in f"{caught.value!r} {caught.value}"


# --- интерфейсы ---


def _public(cls):
    return {
        name: inspect.signature(member)
        for name, member in inspect.getmembers(cls, inspect.isfunction)
        if not name.startswith("_") or name in ("__aenter__", "__aexit__")
    }


@pytest.mark.parametrize(
    ("impl", "protocol"),
    [
        (client_module.Student, protocols.StudentLike),
        (client_module.LoginFlow, protocols.LoginFlowLike),
        (client_module.Login, protocols.LoginLike),
        (client_module.Diary, protocols.DiaryLike),
    ],
)
def test_core_signatures_follow_protocols(impl, protocol):
    ours, expected = _public(impl), _public(protocol)

    assert set(expected) <= set(ours)
    for name, signature in expected.items():
        assert list(signature.parameters) == list(ours[name].parameters), name
        assert [p.default for p in signature.parameters.values()] == [
            p.default for p in ours[name].parameters.values()
        ], name
        assert inspect.iscoroutinefunction(getattr(protocol, name)) == inspect.iscoroutinefunction(
            getattr(impl, name)
        ), name


async def _hang_on(server, token, now, method, path, call):
    """Дневник виснет на запросе method path; возвращает ошибку вызова при deadline."""

    async def answer(request):
        if (request.method, request.url.path) == (method, path):
            await asyncio.Event().wait()
        return server(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    async with Diary(hosts=HOSTS, http=http, deadline=1.0) as diary:
        # Контекст ученика уже в кэше: дедлайн тратится только на проверяемый запрос.
        await diary.student(token).marks()
        with pytest.raises(errors.DiaryError) as caught:
            await call(diary.student(token))
    return caught.value


@pytest.mark.parametrize(
    ("method", "path", "call"),
    [
        ("GET", "/api/usersettings/v1", lambda s: s.update_settings(SETTINGS_UPDATE)),
        (
            "GET",
            f"/api/persondata/v1/persons/{STUDENT.person_guid}",
            lambda s: s.update_contact(2, "new.address@example.test"),
        ),
    ],
)
async def test_deadline_during_read_before_write_is_plain_timeout(
    server, now, token, method, path, call
):
    error = await _hang_on(server, token, now, method, path, call)

    assert type(error) is errors.UpstreamTimeout
    assert server.count("PUT", "/api/usersettings/v1") == 0


@pytest.mark.parametrize("case", WRITE_CASES)
async def test_deadline_during_write_send_is_uncertain(server, now, token, case):
    call, method, path = WRITE_CASES[case]

    error = await _hang_on(server, token, now, method, path, call)

    assert isinstance(error, errors.WriteUncertain)
    assert isinstance(error.cause, errors.UpstreamTimeout)


@pytest.mark.parametrize("name", ["me", "identity"])
async def test_cold_context_profile_is_fetched_once_for_profile_reads(diary, server, token, name):
    call, _ = READS[name]

    await call(diary.student(token))

    # Профиль, из которого собран контекст, не запрашивается второй раз.
    assert server.count("GET", "/api/family/web/v1/profile") == 1


@pytest.mark.parametrize("name", ["me", "identity"])
async def test_warm_context_profile_reads_ask_fresh_profile(diary, server, token, name):
    call, _ = READS[name]
    await diary.student(token).marks()

    await call(diary.student(token))

    # Контекст из кэша мог устареть до 10 минут: профиль для me/identity свежий.
    assert server.count("GET", "/api/family/web/v1/profile") == 2
