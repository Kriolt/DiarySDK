"""Заголовки чтения: токен уходит и в Authorization, и в куки, как у приложения."""

from diarysdk._api.base import Api
from tests.fakes import HOSTS, FakeTransport


async def test_cookie_header_carries_token_twice():
    fake = FakeTransport()
    fake.add("/ping", {})

    await Api(fake, HOSTS, "t.t.t")._get(HOSTS.dnevnik, "/ping", call="ping", headers={})

    sent = fake.sent[0]
    assert sent.header("Cookie") == "aupdtoken=t.t.t; aupd_token=t.t.t"
    assert sent.header("Authorization") == "Bearer t.t.t"
