"""Вход через ЕСИА: свои шаги через настоящий транспорт.

Портал и ЕСИА — один httpx.MockTransport с двумя хостами. Ответы ЕСИА
синтетические, по тому, что известно о протоколе: живых ответов входа пока нет.
"""

import json
import logging

import httpx
import pytest

from diarysdk._hosts import Hosts
from diarysdk._login import esia as login_esia
from diarysdk._port import CaptchaChallenge, EsiaStep, MfaChallenge
from diarysdk._transport import Transport
from diarysdk.errors import (
    BadCaptcha,
    BadCode,
    BadCredentials,
    LoginBlocked,
    UnsupportedStep,
    UpstreamError,
    UpstreamFormat,
)
from tests.tokens import valid_token

LOGIN = "ivanov-esia@example.test"
PASSWORD = "Пароль-госуслуг-42"
CODE = "246813"
ANSWER = "капча-ответ-7Q"
CONTACT = "+7 *** ***-**-12"
MAX_PARAM_CODE = "max-param-code-58"
QUESTION = "Сколько будет два плюс два?"
JWT = valid_token()
PORTAL = "https://portal.test"
ESIA = "https://esia.test"
IMAGE = "О.ЗД1"
QUESTION_TYPE = "О.ЗИ1"


def mfa(kind="SMS", attempts=3, **extra):
    # Форма otp_details — как в живом входе 16.11 (значения выдуманы).
    details = {
        "code_verified": False,
        "phone": CONTACT,
        "verify_attempts_left": attempts,
        "verify_timeout_secs": 300,
        "renew_attempts_left": 5,
        "renew_timeout_secs": 60,
        "code_length": 6,
        "mfa_sms_auto_notification": True,
    }
    return {"action": "ENTER_MFA", "mfa_details": {"type": kind, "otp_details": details, **extra}}


def max_quiz(**extra):
    # Форма max_details — как в живом входе 16.11; поля skippable там нет.
    details = {
        "next_location": "/login/quiz-max",
        "ttl": 600,
        "parameters": {"masked_phone": CONTACT, "code": MAX_PARAM_CODE},
        "active_app": False,
        "already_setup_max": False,
        "quiz_version": 1,
    }
    return {"action": "MAX_QUIZ", "max_details": {**details, **extra}}


SKIP_MAX = "/aas/oauth2/api/login/quiz-max/skip"
SKIP_PASSWORD = "/aas/oauth2/api/login/change-password/skip"


def anomaly(kind=IMAGE, guid="guid-1"):
    return {"action": "SOLVE_ANOMALY_REACTION", "reaction_details": {"type": kind, "guid": guid}}


class Esia:
    """Подставные портал и ЕСИА. answers[путь] — очередь ответов (status, body):
    последний повторяется."""

    def __init__(self):
        self.calls = []
        self.answers = {}
        self.page = "meta"
        self.callback_cookie = True
        self.captcha_sessions = 0

    def answer(self, path, *items):
        self.answers[path] = list(items)

    def client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def reply(self, path):
        queue = self.answers[path]
        status, body = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(body, bytes):
            return httpx.Response(status, content=body, headers={"Content-Type": "text/html"})
        return httpx.Response(status, json=body)

    def note(self, request, body=None):
        self.calls.append(
            {
                "path": request.url.path,
                "query": dict(request.url.params),
                "cookie": request.headers.get("Cookie") or "",
                "captchasession": request.headers.get("captchasession"),
                "body": body,
            }
        )

    async def handle(self, request):
        host, path = request.url.host, request.url.path
        routes = self.portal_routes if host == "portal.test" else self.esia_routes
        if (request.method, path) in routes:
            return routes[request.method, path](request)
        if request.method == "POST" and path in self.esia_posts and host == "esia.test":
            return self.post(request)
        return httpx.Response(404)

    @property
    def portal_routes(self):
        return {
            ("GET", "/v3/auth/esia/login"): self.login_page,
            ("GET", "/v3/auth/esia/callback"): self.callback,
            ("GET", "/"): self.landing,
        }

    @property
    def esia_routes(self):
        return {
            ("GET", "/aas/oauth2/ac"): self.authorize,
            ("GET", "/login/"): self.landing,
            ("GET", "/aas/oauth2/config"): self.config,
            ("GET", "/captcha/api/public/v2/type"): self.captcha_type,
            ("GET", "/captcha/api/public/v2/renew"): self.captcha_type,
            ("GET", "/captcha/api/public/v2/image"): self.captcha_image,
            ("GET", "/anomaly-resolver/api/reaction/question"): self.question,
        }

    esia_posts = (
        "/aas/oauth2/api/login",
        "/aas/oauth2/api/scope/allow",
        "/aas/oauth2/api/login/otp/verify",
        "/aas/oauth2/api/login/totp/verify",
        "/aas/oauth2/api/login/otp-max/verify",
        "/aas/oauth2/api/login/quiz-max/skip",
        "/aas/oauth2/api/login/change-password/skip",
        "/aas/oauth2/api/anomaly/captcha/verify",
        "/aas/oauth2/api/anomaly/question/answer",
        "/captcha/api/public/v2/verify",
    )

    def login_page(self, request):
        self.note(request)
        target = f"{self.esia}/aas/oauth2/ac?client_id=mosreg&amp;state=s-1"
        cookie = {"Set-Cookie": "authedu_session=p-1; Path=/"}
        match self.page:
            case "meta":
                html = f'<html><meta http-equiv="refresh" content="0;url={target}"></html>'
            case "foreign":
                html = '<meta http-equiv="refresh" content="0;url=https://evil.example/ac">'
            case "redirect":
                return httpx.Response(302, headers={"Location": target, **cookie})
            case _:
                html = "<html>техработы</html>"
        return httpx.Response(200, text=html, headers={"Content-Type": "text/html", **cookie})

    def authorize(self, request):
        self.note(request)
        return httpx.Response(
            302, headers={"Location": "/login/", "Set-Cookie": "esia_session=e-1; Path=/"}
        )

    def landing(self, request):
        self.note(request)
        return httpx.Response(200, text="ok")

    def config(self, request):
        self.note(request)
        return httpx.Response(200, json={"oauth": True})

    def post(self, request):
        self.note(request, json.loads(request.content) if request.content else None)
        return self.reply(request.url.path)

    def captcha_type(self, request):
        self.note(request)
        self.captcha_sessions += 1
        return httpx.Response(
            200,
            json={"captchaType": "esiacaptcha", "captchaSession": f"cs-{self.captcha_sessions}"},
        )

    def captcha_image(self, request):
        self.note(request)
        session = request.headers.get("captchasession", "")
        return httpx.Response(
            200, content=f"PNG-{session}".encode(), headers={"Content-Type": "image/png"}
        )

    def question(self, request):
        self.note(request)
        return httpx.Response(200, json={"question_text": QUESTION})

    def callback(self, request):
        self.note(request)
        headers = {"Location": "/"}
        if self.callback_cookie:
            headers["Set-Cookie"] = f"aupd_token={JWT}; Path=/"
        return httpx.Response(302, headers=headers)

    def paths(self):
        return [call["path"] for call in self.calls]

    def call(self, path):
        [found] = [call for call in self.calls if call["path"] == path]
        return found


@pytest.fixture
def esia():
    fake = Esia()
    fake.portal, fake.esia = PORTAL, ESIA
    fake.hosts = Hosts(
        dnevnik=fake.portal, school_api=f"{fake.portal}/api", school=fake.portal, esia=fake.esia
    )
    done = {"action": "DONE", "redirect_url": f"{fake.portal}/v3/auth/esia/callback?code=c-1"}
    fake.done = done
    fake.answer("/aas/oauth2/api/login", (200, done))
    return fake


@pytest.fixture
def records():
    return []


@pytest.fixture
async def transport(esia, records):
    async with Transport(
        user_agent="DiarySDK/test", recorder=records.append, http=esia.client()
    ) as t:
        yield t


async def start(transport, esia):
    return await login_esia.esia_start(transport, esia.hosts, LOGIN, PASSWORD)


def dump(session) -> str:
    """Всё, что поток держит между запросами, включая значения кук."""
    parts = [repr(vars(session))]
    for value in vars(session).values():
        if hasattr(value, "__dataclass_fields__"):
            parts.append(str(vars(value)))
    parts.append(repr([(c.name, c.value) for c in session.cookies._jar.jar]))
    return "\n".join(parts)


async def test_done_at_once_gives_token_and_closes_session(transport, esia):
    session, result = await start(transport, esia)

    assert result == JWT
    assert esia.paths() == [
        "/v3/auth/esia/login",
        "/aas/oauth2/ac",
        "/login/",
        "/aas/oauth2/config",
        "/aas/oauth2/api/login",
        "/v3/auth/esia/callback",
    ]
    assert esia.call("/aas/oauth2/api/login")["body"] == {"login": LOGIN, "password": PASSWORD}
    # &amp; в meta refresh — это & адреса.
    assert esia.call("/aas/oauth2/ac")["query"] == {"client_id": "mosreg", "state": "s-1"}
    # Куки ЕСИА и портала живут в банке потока и уходят со следующими шагами.
    assert "esia_session=e-1" in esia.call("/aas/oauth2/api/login")["cookie"]
    assert "authedu_session=p-1" in esia.call("/v3/auth/esia/callback")["cookie"]
    assert session.waiting is None
    assert len(session.cookies) == 0


async def test_login_page_may_redirect_instead_of_meta_refresh(transport, esia):
    esia.page = "redirect"

    _, result = await start(transport, esia)

    assert result == JWT


async def test_grant_scope_access_is_confirmed(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, {"action": "GRANT_SCOPE_ACCESS"}))
    esia.answer("/aas/oauth2/api/scope/allow", (200, esia.done))

    _, result = await start(transport, esia)

    assert result == JWT
    assert "/aas/oauth2/api/scope/allow" in esia.paths()


async def test_endless_grant_scope_is_format_error(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, {"action": "GRANT_SCOPE_ACCESS"}))
    esia.answer("/aas/oauth2/api/scope/allow", (200, {"action": "GRANT_SCOPE_ACCESS"}))

    with pytest.raises(UpstreamFormat):
        await start(transport, esia)

    assert esia.paths().count("/aas/oauth2/api/scope/allow") == login_esia.MAX_GRANTS


async def test_max_quiz_without_skippable_is_skipped_once(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, max_quiz()))
    esia.answer(SKIP_MAX, (200, esia.done))

    _, result = await start(transport, esia)

    assert result == JWT
    assert esia.paths().count(SKIP_MAX) == 1
    assert esia.call(SKIP_MAX)["body"] == {}
    assert "esia_session=e-1" in esia.call(SKIP_MAX)["cookie"]


async def test_max_quiz_after_code_gives_token(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, mfa()))
    esia.answer("/aas/oauth2/api/login/otp/verify", (200, max_quiz()))
    esia.answer(SKIP_MAX, (200, esia.done))
    session, _ = await start(transport, esia)

    assert await login_esia.esia_code(transport, esia.hosts, session, CODE) == JWT


async def test_max_quiz_not_skippable_is_unsupported_with_hint(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, max_quiz(skippable=False)))

    with pytest.raises(UnsupportedStep) as info:
        await start(transport, esia)

    assert "MAX_QUIZ" in info.value.what
    assert SKIP_MAX not in esia.paths()
    assert "gosuslugi.ru" in info.value.hint


@pytest.mark.parametrize("answer", [(400, {"x": 1}), (200, b"<html>no json</html>"), (404, b"")])
async def test_max_skip_failure_is_not_retried(transport, esia, answer):
    esia.answer("/aas/oauth2/api/login", (200, max_quiz()))
    esia.answer(SKIP_MAX, answer)

    with pytest.raises(UnsupportedStep) as info:
        await start(transport, esia)

    assert "MAX_QUIZ" in info.value.what
    assert esia.paths().count(SKIP_MAX) == 1


async def test_change_password_is_skipped(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, {"action": "CHANGE_PASSWORD"}))
    esia.answer(SKIP_PASSWORD, (200, esia.done))

    _, result = await start(transport, esia)

    assert result == JWT
    assert esia.call(SKIP_PASSWORD)["body"] == {}


async def test_change_password_skip_failure(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, {"action": "CHANGE_PASSWORD"}))
    esia.answer(SKIP_PASSWORD, (400, {"x": 1}))

    with pytest.raises(UnsupportedStep) as info:
        await start(transport, esia)

    assert "CHANGE_PASSWORD" in info.value.what
    assert esia.paths().count(SKIP_PASSWORD) == 1


async def test_max_quiz_then_change_password_then_done(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, max_quiz()))
    esia.answer(SKIP_MAX, (200, {"action": "CHANGE_PASSWORD"}))
    esia.answer(SKIP_PASSWORD, (200, esia.done))

    _, result = await start(transport, esia)

    assert result == JWT


async def test_endless_skips_are_bounded(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, max_quiz()))
    esia.answer(SKIP_MAX, (200, max_quiz()))

    # Четвёртый пропуск — тот же неподдерживаемый шаг с подсказкой, а не
    # безликий сбой формата: потребителю есть что сделать.
    with pytest.raises(UnsupportedStep) as info:
        await start(transport, esia)

    assert "MAX_QUIZ" in info.value.what
    assert info.value.hint == login_esia._MAX_HINT
    assert esia.paths().count(SKIP_MAX) == login_esia.MAX_SKIPS


async def test_endless_password_change_offers_get_their_own_hint(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, {"action": "CHANGE_PASSWORD"}))
    esia.answer(SKIP_PASSWORD, (200, {"action": "CHANGE_PASSWORD"}))

    with pytest.raises(UnsupportedStep) as info:
        await start(transport, esia)

    assert info.value.hint == login_esia._SKIP_HINT


async def test_max_code_goes_to_otp_max_verify(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, mfa("MAX")))
    esia.answer("/aas/oauth2/api/login/otp-max/verify", (200, esia.done))

    session, step = await start(transport, esia)
    assert step.mfa == MfaChallenge(kind="max", contact=CONTACT, ttl=300, attempts_left=3)

    assert await login_esia.esia_code(transport, esia.hosts, session, CODE) == JWT
    assert esia.call("/aas/oauth2/api/login/otp-max/verify")["query"] == {"code": CODE}


async def test_live_otp_details_map_to_step(transport, esia):
    body = mfa(attempts=2)
    body["mfa_details"]["otp_details"]["verify_timeout_secs"] = 120
    esia.answer("/aas/oauth2/api/login", (200, body))

    _, step = await start(transport, esia)

    assert step.mfa == MfaChallenge(kind="sms", contact=CONTACT, ttl=120, attempts_left=2)


async def test_sms_code_step_then_token(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, mfa("SMS")))
    esia.answer("/aas/oauth2/api/login/otp/verify", (200, esia.done))

    session, step = await start(transport, esia)

    assert step == EsiaStep(mfa=MfaChallenge(kind="sms", contact=CONTACT, ttl=300, attempts_left=3))
    assert session.waiting == "mfa"
    # После первого шага у потока нет ни логина, ни пароля.
    assert PASSWORD not in dump(session)
    assert LOGIN not in dump(session)

    token = await login_esia.esia_code(transport, esia.hosts, session, CODE)

    assert token == JWT
    verify = esia.call("/aas/oauth2/api/login/otp/verify")
    assert verify["query"] == {"code": CODE}
    assert "esia_session=e-1" in verify["cookie"]
    assert session.waiting is None


@pytest.mark.parametrize("kind", ["TTP", "TOTP"])
async def test_totp_code_goes_to_totp_verify(transport, esia, kind):
    esia.answer("/aas/oauth2/api/login", (200, mfa(kind)))
    esia.answer("/aas/oauth2/api/login/totp/verify", (200, esia.done))

    session, step = await start(transport, esia)
    assert step.mfa.kind == "totp"

    assert await login_esia.esia_code(transport, esia.hosts, session, CODE) == JWT
    assert esia.call("/aas/oauth2/api/login/totp/verify")["query"] == {"code": CODE}


async def test_mfa_without_details_uses_library_defaults(transport, esia):
    esia.answer(
        "/aas/oauth2/api/login", (200, {"action": "ENTER_MFA", "mfa_details": {"type": "TTP"}})
    )

    _, step = await start(transport, esia)

    assert step.mfa == MfaChallenge(kind="totp", contact=None, ttl=300, attempts_left=3)


@pytest.mark.parametrize("kind", ["PUSH", "EMAIL", None, "пуш с <b>"])
async def test_unknown_mfa_kind_is_unsupported(transport, esia, kind):
    # Незнакомый тип MFA не поддержан.
    esia.answer("/aas/oauth2/api/login", (200, mfa(kind)))

    with pytest.raises(UnsupportedStep) as info:
        await start(transport, esia)

    assert "/aas/oauth2/api/login/totp/verify" not in esia.paths()
    if kind == "PUSH":
        assert "PUSH" in info.value.what
    assert "<b>" not in info.value.what


async def test_wrong_code_keeps_flow_with_fewer_attempts(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, mfa()))
    esia.answer(
        "/aas/oauth2/api/login/otp/verify",
        (200, {"failed": "INVALID_OTP", **mfa(attempts=2)}),
        (200, esia.done),
    )
    session, _ = await start(transport, esia)

    with pytest.raises(BadCode) as info:
        await login_esia.esia_code(transport, esia.hosts, session, "111111")

    assert info.value.step.attempts_left == 2
    assert session.waiting == "mfa"
    assert "111111" not in dump(session)
    assert await login_esia.esia_code(transport, esia.hosts, session, CODE) == JWT


async def test_wrong_code_without_details_counts_attempts_itself(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, mfa(attempts=2)))
    esia.answer("/aas/oauth2/api/login/otp/verify", (400, {"failed": "INVALID_OTP"}))
    session, _ = await start(transport, esia)

    with pytest.raises(BadCode) as info:
        await login_esia.esia_code(transport, esia.hosts, session, "111111")
    assert info.value.step.attempts_left == 1

    with pytest.raises(LoginBlocked):
        await login_esia.esia_code(transport, esia.hosts, session, "222222")
    assert session.waiting is None


async def test_last_wrong_code_blocks_login(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, mfa()))
    esia.answer("/aas/oauth2/api/login/otp/verify", (200, {"failed": "X", **mfa(attempts=0)}))
    session, _ = await start(transport, esia)

    with pytest.raises(LoginBlocked):
        await login_esia.esia_code(transport, esia.hosts, session, "111111")


async def test_image_captcha_then_token(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, anomaly(IMAGE, "guid-1")))
    esia.answer("/captcha/api/public/v2/verify", (200, {"verify_token": "vt-1"}))
    esia.answer("/aas/oauth2/api/anomaly/captcha/verify", (200, esia.done))

    session, step = await start(transport, esia)

    assert step == EsiaStep(
        captcha=CaptchaChallenge(kind="image", image=b"PNG-cs-1", image_type="image/png")
    )
    assert session.waiting == "captcha"

    assert await login_esia.esia_captcha(transport, esia.hosts, session, ANSWER) == JWT
    first = esia.call("/captcha/api/public/v2/verify")
    assert first["body"] == {"answer": ANSWER, "captchaType": "esiacaptcha"}
    assert first["captchasession"] == "cs-1"
    verify = esia.call("/aas/oauth2/api/anomaly/captcha/verify")
    assert verify["query"] == {"guid": "guid-1", "verify_token": "vt-1"}
    assert verify["body"] == {"verify_token": "vt-1", "guid": "guid-1"}


async def test_question_captcha_then_token(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, anomaly(QUESTION_TYPE, "guid-q")))
    esia.answer("/aas/oauth2/api/anomaly/question/answer", (200, esia.done))

    session, step = await start(transport, esia)

    assert step == EsiaStep(captcha=CaptchaChallenge(kind="question", question=QUESTION))
    assert esia.call("/anomaly-resolver/api/reaction/question")["query"] == {"guid": "guid-q"}

    assert await login_esia.esia_captcha(transport, esia.hosts, session, ANSWER) == JWT
    assert esia.call("/aas/oauth2/api/anomaly/question/answer")["body"] == {
        "answer": ANSWER,
        "guid": "guid-q",
    }
    assert ANSWER not in dump(session)


async def test_mfa_then_captcha_then_token(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, mfa()))
    esia.answer("/aas/oauth2/api/login/otp/verify", (200, anomaly(QUESTION_TYPE)))
    esia.answer("/aas/oauth2/api/anomaly/question/answer", (200, esia.done))
    session, _ = await start(transport, esia)

    step = await login_esia.esia_code(transport, esia.hosts, session, CODE)

    assert step.kind == "captcha"
    assert session.waiting == "captcha"
    assert await login_esia.esia_captcha(transport, esia.hosts, session, ANSWER) == JWT


async def test_wrong_image_answer_gives_fresh_image(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, anomaly(IMAGE)))
    esia.answer("/captcha/api/public/v2/verify", (200, {"verify_token": None}))
    session, _ = await start(transport, esia)

    with pytest.raises(BadCaptcha) as info:
        await login_esia.esia_captcha(transport, esia.hosts, session, "не то")

    assert info.value.step.image == b"PNG-cs-2"
    renew = [c for c in esia.calls if c["path"] == "/captcha/api/public/v2/renew"]
    assert renew[0]["captchasession"] == "cs-1"
    # Без verify_token в ЕСИА ничего не уходит.
    assert "/aas/oauth2/api/anomaly/captcha/verify" not in esia.paths()
    assert session.waiting == "captcha"


async def test_failed_captcha_verify_gives_fresh_image(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, anomaly(IMAGE)))
    esia.answer("/captcha/api/public/v2/verify", (200, {"verify_token": "vt-1"}))
    esia.answer("/aas/oauth2/api/anomaly/captcha/verify", (200, {"failed": "WRONG_ANSWER"}))
    session, _ = await start(transport, esia)

    with pytest.raises(BadCaptcha) as info:
        await login_esia.esia_captcha(transport, esia.hosts, session, "не то")

    assert info.value.step.kind == "image"
    assert info.value.step.image == b"PNG-cs-2"


async def test_wrong_question_answer_asks_question_again(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, anomaly(QUESTION_TYPE)))
    esia.answer("/aas/oauth2/api/anomaly/question/answer", (200, {"failed": "WRONG_ANSWER"}))
    session, _ = await start(transport, esia)

    with pytest.raises(BadCaptcha) as info:
        await login_esia.esia_captcha(transport, esia.hosts, session, "не то")

    assert info.value.step == CaptchaChallenge(kind="question", question=QUESTION)


async def test_new_anomaly_after_answer_is_next_step(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, anomaly(QUESTION_TYPE)))
    esia.answer("/aas/oauth2/api/anomaly/question/answer", (200, anomaly(IMAGE, "guid-2")))
    session, _ = await start(transport, esia)

    step = await login_esia.esia_captcha(transport, esia.hosts, session, ANSWER)

    assert step.captcha.kind == "image"


async def test_renew_gives_new_image(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, anomaly(IMAGE)))
    session, _ = await start(transport, esia)

    step = await login_esia.esia_captcha_renew(transport, esia.hosts, session)

    assert step.captcha.image == b"PNG-cs-2"
    assert esia.call("/captcha/api/public/v2/renew")["captchasession"] == "cs-1"


async def test_renew_of_question_asks_it_again(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, anomaly(QUESTION_TYPE)))
    session, _ = await start(transport, esia)

    step = await login_esia.esia_captcha_renew(transport, esia.hosts, session)

    assert step.captcha.question == QUESTION


@pytest.mark.parametrize("kind", ["О.ЗК1", "", None])
async def test_unknown_captcha_kind_is_unsupported(transport, esia, kind):
    esia.answer("/aas/oauth2/api/login", (200, anomaly(kind)))

    with pytest.raises(UnsupportedStep):
        await start(transport, esia)


@pytest.mark.parametrize(
    ("action", "shown"),
    [("PUSH_CONFIRM", "PUSH_CONFIRM"), ("SIGN_WITH_EDS", "SIGN_WITH_EDS"), (f"x {LOGIN}", None)],
)
async def test_unknown_action_is_unsupported_with_esia_name(transport, esia, action, shown):
    esia.answer("/aas/oauth2/api/login", (200, {"action": action}))

    with pytest.raises(UnsupportedStep) as info:
        await start(transport, esia)

    if shown:
        assert shown in info.value.what
    assert LOGIN not in str(info.value)


@pytest.mark.parametrize(
    "answer",
    [
        (200, {"failed": "INVALID_PASSWORD"}),
        (401, {"failed": "INVALID_CREDENTIALS"}),
        (401, b"<html>"),
        (403, {}),
    ],
)
async def test_refused_password_is_bad_credentials(transport, esia, answer):
    esia.answer("/aas/oauth2/api/login", answer)

    with pytest.raises(BadCredentials) as info:
        await start(transport, esia)

    assert PASSWORD not in str(info.value)


@pytest.mark.parametrize(
    "failed", ["ACCOUNT_LOCKED", "LOGIN_BLOCKED", "pswd_method_temp_locked", "BLOCK", "locked"]
)
async def test_blocked_login_is_login_blocked(transport, esia, failed):
    esia.answer("/aas/oauth2/api/login", (200, {"failed": failed}))

    with pytest.raises(LoginBlocked):
        await start(transport, esia)


@pytest.mark.parametrize("failed", ["CLOCK_SKEW", "UNLOCKABLE", "BLOCKCHAIN_ERROR"])
async def test_failed_with_lock_inside_a_word_is_not_a_block(transport, esia, failed):
    # Подстрока LOCK ловила бы CLOCK_…: сравниваем целые слова.
    esia.answer("/aas/oauth2/api/login", (200, {"failed": failed}))

    with pytest.raises(BadCredentials):
        await start(transport, esia)


@pytest.mark.parametrize(
    "answer",
    [
        (200, {}),
        (200, {"action": None}),
        (200, b"<html>"),
        (200, ["DONE"]),
        (200, {"action": "DONE"}),
        (200, {"action": "ENTER_MFA"}),
        (200, {"action": "SOLVE_ANOMALY_REACTION", "reaction_details": {"type": IMAGE}}),
    ],
)
async def test_unexpected_esia_answer_is_format_error(transport, esia, answer):
    esia.answer("/aas/oauth2/api/login", answer)

    with pytest.raises(UpstreamFormat) as info:
        await start(transport, esia)

    assert PASSWORD not in str(info.value)


async def test_done_without_token_cookie_is_format_error(transport, esia):
    esia.callback_cookie = False

    with pytest.raises(UpstreamFormat):
        await start(transport, esia)


async def test_done_to_foreign_host_is_not_followed(transport, esia, records):
    esia.answer(
        "/aas/oauth2/api/login",
        (200, {"action": "DONE", "redirect_url": "https://evil.example/cb"}),
    )

    with pytest.raises(UpstreamFormat) as info:
        await start(transport, esia)

    assert records[-1].call == "login.esia.password"
    assert "evil.example" not in str(info.value)


@pytest.mark.parametrize("page", ["no_meta", "foreign"])
async def test_login_page_without_own_esia_link_is_format_error(transport, esia, records, page):
    # Страница без своей ссылки ЕСИА — upstream_format и ни шагу дальше.
    esia.page = page

    with pytest.raises(UpstreamFormat):
        await start(transport, esia)

    assert [r.call for r in records] == ["login.esia.page"]


async def test_server_error_on_password_is_not_retried(transport, esia):
    esia.answer("/aas/oauth2/api/login", (503, {"failed": "x"}))

    with pytest.raises(UpstreamError) as info:
        await start(transport, esia)

    assert info.value.upstream_status == 503
    assert esia.paths().count("/aas/oauth2/api/login") == 1


async def test_server_error_on_code_is_not_retried(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, mfa()))
    esia.answer("/aas/oauth2/api/login/otp/verify", (502, b"bad gateway"))
    session, _ = await start(transport, esia)

    with pytest.raises(UpstreamError):
        await login_esia.esia_code(transport, esia.hosts, session, CODE)

    assert esia.paths().count("/aas/oauth2/api/login/otp/verify") == 1


async def test_records_have_no_bodies_and_no_secrets(transport, esia, records):
    esia.answer("/aas/oauth2/api/login", (200, mfa()))
    esia.answer("/aas/oauth2/api/login/otp/verify", (200, anomaly(IMAGE)))
    esia.answer("/captcha/api/public/v2/verify", (200, {"verify_token": "vt-1"}))
    esia.answer("/aas/oauth2/api/anomaly/captcha/verify", (200, esia.done))
    session, _ = await start(transport, esia)
    await login_esia.esia_code(transport, esia.hosts, session, CODE)
    await login_esia.esia_captcha(transport, esia.hosts, session, ANSWER)

    assert all(r.body == b"" and r.attempts == 1 for r in records)
    text = repr(records)
    for value in (LOGIN, PASSWORD, CODE, ANSWER, CONTACT, MAX_PARAM_CODE, JWT):
        assert value not in text


async def test_log_has_no_secrets_on_any_outcome(transport, esia, caplog):
    esia.answer("/aas/oauth2/api/login", (200, mfa()))
    esia.answer(
        "/aas/oauth2/api/login/otp/verify",
        (200, {"failed": "INVALID_OTP", **mfa(attempts=2)}),
        (200, anomaly(QUESTION_TYPE)),
    )
    esia.answer(
        "/aas/oauth2/api/anomaly/question/answer", (200, {"failed": "WRONG"}), (200, esia.done)
    )
    with caplog.at_level(logging.DEBUG):
        session, _ = await start(transport, esia)
        with pytest.raises(BadCode):
            await login_esia.esia_code(transport, esia.hosts, session, "111111")
        await login_esia.esia_code(transport, esia.hosts, session, CODE)
        with pytest.raises(BadCaptcha):
            await login_esia.esia_captcha(transport, esia.hosts, session, "не то")
        await login_esia.esia_captcha(transport, esia.hosts, session, ANSWER)

    ours = caplog.records
    assert ours
    text = "\n".join(f"{r.getMessage()} {vars(r)}" for r in ours)
    for value in (LOGIN, PASSWORD, CODE, "111111", ANSWER, "не то", CONTACT, QUESTION, JWT):
        assert value not in text
        assert json.dumps(value)[1:-1] not in text


@pytest.mark.parametrize("stage", ["password", "code", "captcha"])
async def test_skip_with_failed_closes_flow_without_bad_answer(transport, esia, stage):
    # failed в ответе на пропуск не относится к паролю, коду или капче.
    quiz = (200, max_quiz())
    if stage == "password":
        esia.answer("/aas/oauth2/api/login", quiz)
    else:
        esia.answer("/aas/oauth2/api/login", (200, mfa()), (200, mfa()))
        esia.answer(
            "/aas/oauth2/api/login/otp/verify", (200, anomaly()) if stage == "captcha" else quiz
        )
        esia.answer("/captcha/api/public/v2/verify", (200, {"verify_token": "vt-1"}))
        esia.answer("/aas/oauth2/api/anomaly/captcha/verify", quiz)
    esia.answer(SKIP_MAX, (400, {"failed": "X"}))
    with pytest.raises(UnsupportedStep) as info:
        session, _ = await start(transport, esia)
        if stage == "code":
            await login_esia.esia_code(transport, esia.hosts, session, CODE)
        if stage == "captcha":
            await login_esia.esia_code(transport, esia.hosts, session, CODE)
            await login_esia.esia_captcha(transport, esia.hosts, session, ANSWER)
    assert info.value.hint
    assert esia.paths().count(SKIP_MAX) == 1


async def test_skip_4xx_with_action_is_unsupported_once(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, max_quiz()))
    esia.answer(SKIP_MAX, (400, max_quiz()))

    with pytest.raises(UnsupportedStep) as info:
        await start(transport, esia)

    assert info.value.hint
    assert esia.paths().count(SKIP_MAX) == 1


async def test_skip_200_with_failed_is_unsupported(transport, esia):
    esia.answer("/aas/oauth2/api/login", (200, max_quiz()))
    esia.answer(SKIP_MAX, (200, {"failed": "X"}))

    with pytest.raises(UnsupportedStep):
        await start(transport, esia)


@pytest.mark.parametrize("skip", [SKIP_MAX, SKIP_PASSWORD])
async def test_skip_server_error_is_outage_not_hint(transport, esia, skip):
    first = max_quiz() if skip == SKIP_MAX else {"action": "CHANGE_PASSWORD"}
    esia.answer("/aas/oauth2/api/login", (200, first))
    esia.answer(skip, (503, {"x": 1}))

    with pytest.raises(UpstreamError):
        await start(transport, esia)

    assert esia.paths().count(skip) == 1
