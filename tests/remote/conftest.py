import pytest
from httpx import ASGITransport

from diarysdk._port import EsiaStep
from diarysdk.server.app import create_app
from diarysdk.server.keys import hash_key
from tests.conftest import API_KEY
from tests.fakes import core_diary
from tests.remote.esia import FRESH, IMAGE, LOGIN_KEY, SMS, EsiaDiary, Session
from tests.remote.helpers import remote_diary
from tests.tokens import valid_token


@pytest.fixture
def sleeps(monkeypatch):
    """Паузы повторов не ждём, но записываем: по ним видно, что клиент ждал."""
    import asyncio
    import time

    waited: list[float] = []

    async def fake_async(seconds):
        waited.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_async)
    monkeypatch.setattr(time, "sleep", waited.append)
    return waited


@pytest.fixture
def asgi_app(settings, fake_diary, today):
    return create_app(settings, diary=core_diary(fake_diary))


@pytest.fixture
async def asgi_client(asgi_app):
    async with remote_diary("http://t", API_KEY, transport=ASGITransport(asgi_app)) as c:
        yield c


@pytest.fixture
def jwt():
    return valid_token()


@pytest.fixture
def session():
    return Session("captcha")


@pytest.fixture
def fake_diary(session, jwt):
    return EsiaDiary(
        esia_start=(session, EsiaStep(captcha=IMAGE)),
        esia_captcha=EsiaStep(mfa=SMS),
        esia_captcha_renew=EsiaStep(captcha=FRESH),
        esia_code=jwt,
        password_login=jwt,
    )


@pytest.fixture
def app(settings, keys_file, fake_diary, today):
    keys_file.write_text(f"tests {hash_key('test-key')}\nbot {hash_key(LOGIN_KEY)} login\n")
    return create_app(settings, diary=core_diary(fake_diary))


@pytest.fixture
async def api(app):
    async with remote_diary("http://t", LOGIN_KEY, transport=ASGITransport(app)) as c:
        yield c
