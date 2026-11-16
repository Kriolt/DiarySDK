import logging

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from diarysdk._transport import RatingOff
from diarysdk.errors import (
    MultipleChildren,
    NoAvatar,
    NotFound,
    TokenInvalid,
    UpstreamError,
    UpstreamFormat,
    UpstreamTimeout,
)
from diarysdk.server.app import create_app
from tests.conftest import AUTH_HEADERS
from tests.fakes import FakeDiary, core_diary

ERRORS = {
    "auth": TokenInvalid(status=403),
    "not-found": NotFound(),
    "no-avatar": NoAvatar(),
    "children": MultipleChildren(),
    "unavailable": UpstreamError(upstream_status=500),
    "network": UpstreamError(upstream_status=None),
    "format": UpstreamFormat(problems=["payload.0.id: int_parsing"]),
    "rating": RatingOff(),
    "timeout": UpstreamTimeout(),
}

router = APIRouter()


@router.get("/raise/{name}")
async def raise_error(name: str):
    raise ERRORS[name]


@pytest.fixture
async def client(settings):
    app = create_app(settings, diary=core_diary(FakeDiary()), routers=[router])
    transport = ASGITransport(app)
    async with AsyncClient(transport=transport, base_url="http://t", headers=AUTH_HEADERS) as c:
        yield c


@pytest.mark.parametrize(
    ("name", "status", "code"),
    [
        ("auth", 401, "token_invalid"),
        ("not-found", 404, "not_found"),
        ("no-avatar", 404, "no_avatar"),
        ("children", 422, "multiple_children"),
        ("unavailable", 502, "upstream_error"),
        ("format", 502, "upstream_format"),
        ("rating", 502, "upstream_error"),
        ("timeout", 504, "upstream_timeout"),
    ],
)
async def test_diary_error_becomes_contract_error(client, name, status, code):
    response = await client.get(f"/v1/raise/{name}")

    assert response.status_code == status
    assert response.json()["error"] == code
    assert response.json()["message"]


async def test_rating_off_keeps_old_body_without_upstream_status(client):
    response = await client.get("/v1/raise/rating")

    assert response.status_code == 502
    assert response.json()["error"] == "upstream_error"
    assert "upstream_status" not in response.json()


async def test_upstream_error_carries_upstream_status(client):
    assert (await client.get("/v1/raise/unavailable")).json()["upstream_status"] == 500
    assert (await client.get("/v1/raise/network")).json()["upstream_status"] is None


async def test_format_error_is_logged_for_us_but_not_shown(client, caplog):
    with caplog.at_level(logging.WARNING):
        response = await client.get("/v1/raise/format")

    assert "payload.0.id" not in response.text
    [record] = [r for r in caplog.records if r.getMessage() == "ответ дневника не разобрался"]
    assert record.problems == ["payload.0.id: int_parsing"]
