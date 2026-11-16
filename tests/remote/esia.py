"""Общее для клиентских тестов входа: ключ входа, шаги ЕСИА, подставной дневник."""

from diarysdk._port import CaptchaChallenge, EsiaStep, MfaChallenge
from tests.fakes import FakeDiary

LOGIN_KEY = "login-key"
SMS = MfaChallenge(kind="sms", contact="+7 *** ***-**-12", ttl=300, attempts_left=3)
IMAGE = CaptchaChallenge(kind="image", image=b"\x89PNG-1", image_type="image/png")
FRESH = CaptchaChallenge(kind="image", image=b"\x89PNG-2", image_type="image/png")


class Session:
    def __init__(self, waiting):
        self.waiting = waiting
        self.closed = 0

    def close(self):
        self.closed += 1


class EsiaDiary(FakeDiary):
    """Дневник ЕСИА: после верной капчи сессия ждёт код, как настоящая."""

    async def esia_captcha(self, session, answer):
        result = await FakeDiary.__getattr__(self, "esia_captcha")(session, answer)
        if isinstance(result, EsiaStep) and result.mfa:
            session.waiting = "mfa"
        return result
