import asyncio
import base64
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from diarysdk import client as client_module
from diarysdk._port import CaptchaChallenge, EsiaStep, MfaChallenge
from diarysdk.errors import (
    BadCaptcha,
    BadCode,
    BadCredentials,
    DiaryError,
    LoginBlocked,
    UnsupportedStep,
    UpstreamError,
    UpstreamFormat,
    UpstreamTimeout,
    to_response,
)
from diarysdk.models.auth import LoginMfa, LoginStep
from diarysdk.server.services.login import LoginService
from diarysdk.server.services.login_flows import LoginFlows
from tests.fakes import FakeDiary, core_diary
from tests.tokens import make_token


class SlowDiary:
    async def password_login(self, login, password):
        await asyncio.sleep(1)


async def test_password_login_is_cut_at_deadline():
    service = LoginService(core_diary(SlowDiary(), deadline=0.05))

    with pytest.raises(UpstreamTimeout):
        await service.password("ivanov", "secret")


async def test_password_login_gives_token_with_expiry():
    exp = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
    token = make_token(exp)
    service = LoginService(core_diary(FakeDiary(password_login=token)))

    result = await service.password("ivanov", "secret")

    assert (result.token, result.expires_at, result.method) == (token, exp, "password")


@pytest.mark.parametrize(
    ("claims", "roles"),
    [
        ({"rol": "student, parent"}, ["student", "parent"]),
        ({"rol": ""}, []),
        ({"roles": ["student", 7]}, ["student", "7"]),
        ({"rol": 5}, []),
    ],
)
def test_token_info_reads_claims(claims, roles):
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    token = make_token(now + timedelta(seconds=90.5), sub=1000001, **claims)

    info = LoginService(core_diary(FakeDiary()), now=lambda: now).token_info(token)

    assert info.expires_in == 90
    assert info.subject_id == "1000001"
    assert info.roles == roles


@pytest.mark.parametrize(
    ("sub", "subject_id"), [(True, None), (False, None), (7, "7"), ("u1", "u1")]
)
def test_token_info_subject_is_not_a_bool(sub, subject_id):
    # bool — подкласс int: без отдельной проверки True стал бы субъектом «True».
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    token = make_token(now + timedelta(hours=1), sub=sub)

    info = LoginService(core_diary(FakeDiary()), now=lambda: now).token_info(token)

    assert info.subject_id == subject_id


# --- Вход через ЕСИА: потоки между шагами ---

PASSWORD = "Пароль-госуслуг-42"
CODE = "246813"
ANSWER = "капча-ответ-7Q"
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
JWT = make_token(NOW + timedelta(hours=1))
SMS = MfaChallenge(kind="sms", contact="+7 *** ***-**-12", ttl=300, attempts_left=3)
IMAGE = CaptchaChallenge(kind="image", image=b"\x89PNG-1", image_type="image/png")


class Session:
    def __init__(self, waiting="mfa"):
        self.waiting = waiting
        self.closed = 0

    def close(self):
        self.closed += 1
        self.waiting = None


class EsiaDiary:
    """Подставной дневник для ЕСИА: ответы шагов — очередью, последний повторяется."""

    def __init__(self, start=None, **steps):
        self.session = Session()
        self.start = start if start is not None else EsiaStep(mfa=SMS)
        self.steps = {name: list(answers) for name, answers in steps.items()}
        self.calls = []
        self.active = 0
        self.max_active = 0
        self.pause = 0.0

    async def esia_start(self, login, password):
        self.calls.append(("start", login, password))
        if isinstance(self.start, BaseException):
            raise self.start
        return self.session, self.start

    async def _step(self, name, session, *args):
        self.calls.append((name, *args))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.pause)
        finally:
            self.active -= 1
        queue = self.steps[name]
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, EsiaStep):
            session.waiting = answer.kind
        return answer

    async def esia_code(self, session, code):
        return await self._step("code", session, code)

    async def esia_captcha(self, session, answer):
        return await self._step("captcha", session, answer)

    async def esia_captcha_renew(self, session):
        return await self._step("renew", session)


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """Часы ядра и реестра — одни, и стоят на месте, пока тест их не сдвинет."""
    clock = Clock()
    monkeypatch.setattr(client_module, "_utcnow", clock)
    return clock


def esia_service(diary, flows=None, deadline=20.0, **kwargs):
    flows = flows or LoginFlows(now=lambda: NOW)
    core = core_diary(diary, deadline=deadline)
    return LoginService(core, flows=flows, now=lambda: NOW, **kwargs), flows


async def test_esia_start_with_mfa_gives_step_and_keeps_flow():
    diary = EsiaDiary()
    service, flows = esia_service(diary)

    step = await service.esia_start("bot", "ivanov", PASSWORD)

    assert step == LoginStep(
        flow_id=step.flow_id,
        step="mfa",
        expires_at=NOW + timedelta(minutes=5),
        mfa=LoginMfa(kind="sms", contact="+7 *** ***-**-12", ttl=300, attempts_left=3),
    )
    flow = await flows.find("bot", step.flow_id)
    assert flow.login is not None
    # В потоке — только потребитель, срок и сессия.
    assert PASSWORD not in repr(vars(flow))


async def test_esia_start_with_token_leaves_no_flow():
    service, flows = esia_service(EsiaDiary(start=JWT))

    token = await service.esia_start("bot", "ivanov", PASSWORD)

    assert (token.token, token.method, token.expires_at) == (JWT, "esia", NOW + timedelta(hours=1))
    assert len(flows) == 0


async def test_esia_code_to_token_closes_flow():
    diary = EsiaDiary(code=[JWT])
    service, flows = esia_service(diary)
    step = await service.esia_start("bot", "ivanov", PASSWORD)

    token = await service.esia_code("bot", step.flow_id, CODE)

    assert token.method == "esia"
    assert diary.calls[-1] == ("code", CODE)
    assert diary.session.closed == 1
    assert len(flows) == 0


async def test_image_captcha_step_is_base64():
    diary = EsiaDiary(code=[EsiaStep(captcha=IMAGE)])
    service, _ = esia_service(diary)
    step = await service.esia_start("bot", "ivanov", PASSWORD)

    captcha = await service.esia_code("bot", step.flow_id, CODE)

    assert captcha.step == "captcha"
    assert captcha.mfa is None
    assert base64.b64decode(captcha.captcha.image_base64) == b"\x89PNG-1"
    assert captcha.captcha.image_type == "image/png"
    assert captcha.flow_id == step.flow_id


async def test_bad_code_keeps_flow_and_shows_attempts_left():
    diary = EsiaDiary(code=[BadCode(step=replace(SMS, attempts_left=2)), JWT])
    service, flows = esia_service(diary)
    step = await service.esia_start("bot", "ivanov", PASSWORD)

    with pytest.raises(DiaryError) as info:
        await service.esia_code("bot", step.flow_id, "111111")

    assert (info.value.http_status, info.value.code) == (401, "bad_code")
    assert to_response(info.value)[1]["step"]["mfa"]["attempts_left"] == 2
    assert to_response(info.value)[1]["step"]["flow_id"] == step.flow_id
    assert "111111" not in repr(to_response(info.value)[1])
    assert diary.session.closed == 0
    assert (await flows.find("bot", step.flow_id)).login is not None
    assert (await service.esia_code("bot", step.flow_id, CODE)).method == "esia"


async def test_bad_captcha_gives_fresh_captcha_in_error():
    fresh = replace(IMAGE, image=b"\x89PNG-2")
    diary = EsiaDiary(start=EsiaStep(captcha=IMAGE), captcha=[BadCaptcha(step=fresh)])
    diary.session.waiting = "captcha"
    service, flows = esia_service(diary)
    step = await service.esia_start("bot", "ivanov", PASSWORD)

    with pytest.raises(DiaryError) as info:
        await service.esia_captcha("bot", step.flow_id, "не то")

    assert (info.value.http_status, info.value.code) == (401, "bad_captcha")
    next_step = to_response(info.value)[1]["step"]
    assert next_step["step"] == "captcha"
    assert base64.b64decode(next_step["captcha"]["image_base64"]) == b"\x89PNG-2"
    assert (await flows.find("bot", step.flow_id)).login is not None


@pytest.mark.parametrize(
    "error",
    [
        LoginBlocked(),
        UnsupportedStep("PUSH"),
        UpstreamError(upstream_status=503),
        UpstreamFormat(problems=["x"]),
    ],
)
async def test_other_step_failures_drop_the_flow(error):
    diary = EsiaDiary(code=[error])
    service, flows = esia_service(diary)
    step = await service.esia_start("bot", "ivanov", PASSWORD)

    with pytest.raises(type(error)):
        await service.esia_code("bot", step.flow_id, CODE)

    assert diary.session.closed == 1
    assert len(flows) == 0
    with pytest.raises(DiaryError) as info:
        await service.esia_code("bot", step.flow_id, CODE)
    assert info.value.code == "flow_expired"


async def test_slow_step_is_cut_at_deadline_and_drops_flow():
    diary = EsiaDiary(code=[JWT])
    service, flows = esia_service(diary, deadline=0.05)
    step = await service.esia_start("bot", "ivanov", PASSWORD)
    diary.pause = 1

    with pytest.raises(UpstreamTimeout):
        await service.esia_code("bot", step.flow_id, CODE)

    assert len(flows) == 0


async def test_failed_start_frees_its_place():
    diary = EsiaDiary(start=BadCredentials())
    service, flows = esia_service(diary)

    for _ in range(4):
        with pytest.raises(BadCredentials):
            await service.esia_start("bot", "ivanov", PASSWORD)

    assert len(flows) == 0


async def test_fourth_open_flow_is_refused_before_esia():
    diary = EsiaDiary()
    service, _ = esia_service(diary)
    for _ in range(3):
        await service.esia_start("bot", "ivanov", PASSWORD)

    with pytest.raises(DiaryError) as info:
        await service.esia_start("bot", "ivanov", PASSWORD)

    assert info.value.code == "rate_limited"
    # Пароль в ЕСИА не ушёл: место кончилось раньше.
    assert len(diary.calls) == 3


async def test_step_of_other_kind_is_bad_request_and_keeps_flow():
    diary = EsiaDiary(code=[JWT])
    service, flows = esia_service(diary)
    step = await service.esia_start("bot", "ivanov", PASSWORD)

    with pytest.raises(DiaryError) as info:
        await service.esia_captcha("bot", step.flow_id, ANSWER)
    with pytest.raises(DiaryError) as renew:
        await service.esia_captcha_renew("bot", step.flow_id)

    assert (info.value.http_status, info.value.code) == (400, "bad_request")
    assert renew.value.code == "bad_request"
    assert ANSWER not in info.value.message
    assert diary.calls == [("start", "ivanov", PASSWORD)]
    assert await flows.find("bot", step.flow_id)


async def test_foreign_consumer_cannot_use_or_cancel_flow():
    diary = EsiaDiary(code=[JWT])
    service, flows = esia_service(diary)
    step = await service.esia_start("bot", "ivanov", PASSWORD)

    with pytest.raises(DiaryError) as info:
        await service.esia_code("site", step.flow_id, CODE)
    await service.esia_cancel("site", step.flow_id)

    assert info.value.code == "flow_expired"
    assert (await flows.find("bot", step.flow_id)).login is not None


async def test_cancel_closes_flow_and_is_idempotent():
    diary = EsiaDiary()
    service, flows = esia_service(diary)
    step = await service.esia_start("bot", "ivanov", PASSWORD)

    await service.esia_cancel("bot", step.flow_id)
    await service.esia_cancel("bot", step.flow_id)
    await service.esia_cancel("bot", "no-such-flow")

    assert diary.session.closed == 1
    assert len(flows) == 0


async def test_concurrent_steps_of_one_flow_go_one_after_another():
    diary = EsiaDiary(code=[JWT])
    service, _ = esia_service(diary)
    step = await service.esia_start("bot", "ivanov", PASSWORD)
    diary.pause = 0.05

    first, second = await asyncio.gather(
        service.esia_code("bot", step.flow_id, CODE),
        service.esia_code("bot", step.flow_id, "999999"),
        return_exceptions=True,
    )

    assert first.method == "esia"
    # Второй дождался первого и увидел закрытый поток: его код не ушёл никуда.
    assert isinstance(second, DiaryError) and second.code == "flow_expired"
    assert diary.max_active == 1
    assert [c for c in diary.calls if c[0] == "code"] == [("code", CODE)]


async def test_renew_gives_new_captcha_step():
    fresh = replace(IMAGE, image=b"\x89PNG-2")
    diary = EsiaDiary(start=EsiaStep(captcha=IMAGE), renew=[EsiaStep(captcha=fresh)])
    diary.session.waiting = "captcha"
    service, _ = esia_service(diary)
    step = await service.esia_start("bot", "ivanov", PASSWORD)

    renewed = await service.esia_captcha_renew("bot", step.flow_id)

    assert base64.b64decode(renewed.captcha.image_base64) == b"\x89PNG-2"


async def test_close_closes_open_flows():
    diary = EsiaDiary()
    service, flows = esia_service(diary)
    await service.esia_start("bot", "ivanov", PASSWORD)

    await service.close()

    assert diary.session.closed == 1
    assert len(flows) == 0


# --- Шаг идёт долго: отмена, истечение, очередь, остановка ---


class GatedDiary(EsiaDiary):
    """Шаг входа стоит на событии: тест решает, когда он закончится."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gate = asyncio.Event()
        self.started = asyncio.Event()

    async def _step(self, name, session, *args):
        self.started.set()
        await self.gate.wait()
        return await super()._step(name, session, *args)


async def test_cancel_during_step_waits_for_it_then_drops_flow():
    diary = GatedDiary(code=[EsiaStep(captcha=IMAGE)])
    service, flows = esia_service(diary)
    step = await service.esia_start("bot", "ivanov", PASSWORD)
    running = asyncio.create_task(service.esia_code("bot", step.flow_id, CODE))
    await diary.started.wait()

    cancel = asyncio.create_task(service.esia_cancel("bot", step.flow_id))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # DELETE ждёт шаг: поток пока жив, сессия не закрыта под шагом.
    assert not cancel.done()
    assert diary.session.closed == 0
    diary.gate.set()
    result = await running
    await cancel

    assert result.step == "captcha"
    assert diary.session.closed == 1
    assert len(flows) == 0


async def test_expiry_during_step_does_not_drop_busy_flow(clock):
    diary = GatedDiary(code=[EsiaStep(captcha=IMAGE)])
    flows = LoginFlows(now=clock)
    service = LoginService(core_diary(diary), flows=flows, now=clock)
    step = await service.esia_start("bot", "ivanov", PASSWORD)
    running = asyncio.create_task(service.esia_code("bot", step.flow_id, CODE))
    await diary.started.wait()

    # Срок вышел, пока шаг идёт: уборка занятый поток не трогает.
    clock.now += timedelta(minutes=6)
    await flows.sweep()
    assert diary.session.closed == 0
    diary.gate.set()
    result = await running

    # Шаг закончился — срок отсчитывается заново от него.
    assert result.expires_at == clock.now + timedelta(minutes=5)
    assert (await flows.find("bot", step.flow_id)).login is not None


async def test_flow_expired_while_queued_second_step_is_flow_expired(clock):
    diary = GatedDiary(code=[RuntimeError("сбой")])
    flows = LoginFlows(now=clock)
    service = LoginService(core_diary(diary), flows=flows, now=clock)
    step = await service.esia_start("bot", "ivanov", PASSWORD)
    first = asyncio.create_task(service.esia_code("bot", step.flow_id, CODE))
    await diary.started.wait()
    second = asyncio.create_task(service.esia_code("bot", step.flow_id, "999999"))
    await asyncio.sleep(0)

    diary.gate.set()
    with pytest.raises(RuntimeError):
        await first
    with pytest.raises(DiaryError) as info:
        await second

    # Первый шаг сорвался и закрыл поток: второму код уходить некуда.
    assert info.value.code == "flow_expired"
    assert [c for c in diary.calls if c[0] == "code"] == [("code", CODE)]


async def test_queued_step_waits_at_most_lock_wait():
    diary = GatedDiary(code=[EsiaStep(captcha=IMAGE)])
    service, flows = esia_service(diary, lock_wait=0.05)
    step = await service.esia_start("bot", "ivanov", PASSWORD)
    first = asyncio.create_task(service.esia_code("bot", step.flow_id, CODE))
    await diary.started.wait()

    with pytest.raises(DiaryError) as info:
        await service.esia_code("bot", step.flow_id, "999999")

    # Второй не висит вечно (и не ждёт ещё свой шаг), а первый не пострадал.
    assert info.value.code == "flow_expired"
    assert diary.session.closed == 0
    diary.gate.set()
    assert (await first).step == "captcha"
    assert (await flows.find("bot", step.flow_id)).login is not None
    assert [c for c in diary.calls if c[0] == "code"] == [("code", CODE)]


async def test_cancel_is_silent_when_step_holds_lock_past_lock_wait():
    diary = GatedDiary(code=[EsiaStep(captcha=IMAGE)])
    service, _ = esia_service(diary, lock_wait=0.05)
    step = await service.esia_start("bot", "ivanov", PASSWORD)
    first = asyncio.create_task(service.esia_code("bot", step.flow_id, CODE))
    await diary.started.wait()

    # Отмена не висит за идущим шагом дольше lock_wait и всё равно успешна
    # (маршрут отвечает 204); шаг не пострадал.
    async with asyncio.timeout(5):
        await service.esia_cancel("bot", step.flow_id)
    assert diary.session.closed == 0
    diary.gate.set()
    assert (await first).step == "captcha"


async def test_close_during_first_step_does_not_leave_session_behind():
    diary = GatedDiary()
    service, flows = esia_service(diary)

    # esia_start у EsiaDiary не ждёт события, поэтому подменяем его.
    async def slow_start(login, password):
        diary.started.set()
        await diary.gate.wait()
        return diary.session, diary.start

    diary.esia_start = slow_start
    starting = asyncio.create_task(service.esia_start("bot", "ivanov", PASSWORD))
    await diary.started.wait()

    await service.close()
    diary.gate.set()
    with pytest.raises(DiaryError) as info:
        await starting

    assert info.value.code == "flow_expired"
    assert diary.session.closed == 1
    assert len(flows) == 0
