"""Запись не идёт по переадресации: 3xx на PUT/POST/DELETE — WriteUncertain.

Настоящий транспорт против MockTransport: клиент, идущий по переадресациям,
повторил бы запись по Location, и конец цепочки на 2xx сошёл бы за успех.
"""

import httpx
import pytest

from diarysdk._api import raw
from diarysdk._hosts import Hosts
from diarysdk._transport import Transport
from diarysdk.errors import UpstreamError, WriteUncertain
from tests.fakes import DIARY_TOKEN, STUDENT

BASE = "https://diary.test"


class Diary:
    def __init__(self, status):
        self.status = status
        self.requests = []
        self.landed = []
        self.hosts = Hosts(dnevnik=BASE, school_api=BASE, school=BASE)
        self.code = status

    def client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def handle(self, request):
        if request.url.path == "/landing":
            self.landed.append((request.method, request.url.path))
            return httpx.Response(200, json={"success": True})
        self.requests.append((request.method, request.url.path))
        return httpx.Response(self.status, headers={"Location": "/landing"})


@pytest.fixture(params=[301, 302, 307, 308])
def served(request):
    return Diary(request.param)


@pytest.fixture
async def transport(served):
    async with Transport(
        user_agent="DiarySDK/test", retry_pause=0.01, http=served.client()
    ) as transport:
        yield transport


def writes(diary, transport):
    token, student = DIARY_TOKEN, STUDENT
    return {
        "put_contact": lambda: raw.put_contact(
            transport, diary.hosts, token, student, 2, {"id": 2, "data": "a@b.test"}
        ),
        "put_user_settings": lambda: raw.put_user_settings(
            transport, diary.hosts, token, student, {"goal": True}
        ),
        "homework_done": lambda: raw.homework_done(
            transport, diary.hosts, token, student, 555, True
        ),
        "homework_undone": lambda: raw.homework_done(
            transport, diary.hosts, token, student, 555, False
        ),
    }


@pytest.mark.parametrize(
    "name", ["put_contact", "put_user_settings", "homework_done", "homework_undone"]
)
async def test_redirect_on_write_is_write_uncertain_and_sent_once(served, transport, name):
    with pytest.raises(WriteUncertain) as caught:
        await writes(served, transport)[name]()

    # Запись ушла, а чем она кончилась, неизвестно: исход за переадресацией не виден.
    assert isinstance(caught.value.cause, UpstreamError)
    assert caught.value.cause.upstream_status == served.code
    assert caught.value.upstream_status == served.code
    assert len(served.requests) == 1
    assert served.landed == []
