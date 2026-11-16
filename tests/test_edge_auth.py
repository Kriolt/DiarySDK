from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, Request
from httpx import ASGITransport, AsyncClient

from diarysdk.server.app import create_app
from diarysdk.server.edge.auth import require_scope, require_token
from diarysdk.server.keys import hash_key
from tests.conftest import KEY_HEADERS, TOKEN
from tests.tokens import make_token, valid_token

router = APIRouter()


@router.get("/whoami")
async def whoami(request: Request):
    return {"consumer": request.state.consumer}


@router.get("/login-only", dependencies=[Depends(require_scope("login"))])
async def login_only():
    return {"ok": True}


@pytest.fixture
async def client(settings, keys_file):
    keys_file.write_text(f"bot {hash_key('bot-key')}\nbot {hash_key('login-key')} login\n")
    app = create_app(settings, routers=[router])
    async with AsyncClient(transport=ASGITransport(app), base_url="http://diarysdk.test") as c:
        yield c


async def test_missing_api_key_is_forbidden(client):
    response = await client.get("/v1/whoami")

    assert response.status_code == 403
    assert response.json()["error"] == "bad_api_key"


async def test_unknown_api_key_is_forbidden(client):
    response = await client.get("/v1/whoami", headers={"X-Api-Key": "someone-else"})

    assert response.status_code == 403
    assert response.json()["error"] == "bad_api_key"


async def test_known_api_key_names_consumer(client):
    response = await client.get(
        "/v1/whoami", headers={"X-Api-Key": "bot-key", "Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 200
    assert response.json() == {"consumer": "bot"}


async def test_scope_missing_is_forbidden_scope(client):
    response = await client.get(
        "/v1/login-only", headers={"X-Api-Key": "bot-key", "Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 403
    assert response.json()["error"] == "forbidden_scope"


async def test_scope_present_passes(client):
    response = await client.get(
        "/v1/login-only", headers={"X-Api-Key": "login-key", "Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 200


async def test_scope_check_still_rejects_bad_key_first(client):
    response = await client.get("/v1/login-only", headers={"X-Api-Key": "nope"})

    assert response.json()["error"] == "bad_api_key"


async def test_healthz_needs_no_key(client):
    response = await client.get("/healthz")

    assert response.status_code == 200


token_router = APIRouter()


@token_router.get("/token-tag")
async def token_tag(request: Request, token: Annotated[str, Depends(require_token)]):
    return {"tag": request.state.token_tag, "length": len(token)}


@pytest.fixture
async def token_client(settings):
    app = create_app(settings, routers=[token_router])
    transport = ASGITransport(app)
    async with AsyncClient(transport=transport, base_url="http://t", headers=KEY_HEADERS) as c:
        yield c


async def test_missing_token_is_token_missing(token_client):
    response = await token_client.get("/v1/token-tag")

    assert response.status_code == 401
    assert response.json()["error"] == "token_missing"


@pytest.mark.parametrize(
    "authorization",
    ["Basic dXNlcjpwYXNz", "Bearer", "Bearer abc", f"Bearer {make_token(sub='1')}", "Bearer a.b"],
)
async def test_garbage_token_is_token_invalid(token_client, authorization):
    response = await token_client.get("/v1/token-tag", headers={"Authorization": authorization})

    assert response.status_code == 401
    assert response.json()["error"] == "token_invalid"


async def test_expired_token_is_token_expired(token_client):
    token = make_token(datetime.now(UTC) - timedelta(minutes=1))

    response = await token_client.get("/v1/token-tag", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error"] == "token_expired"


async def test_valid_token_passes_and_is_tagged(token_client):
    token = valid_token()

    response = await token_client.get("/v1/token-tag", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"tag": hash_key(token)[:12], "length": len(token)}


async def test_api_key_is_checked_before_token(settings):
    app = create_app(settings, routers=[token_router])
    async with AsyncClient(transport=ASGITransport(app), base_url="http://t") as client:
        response = await client.get("/v1/token-tag")

    assert response.status_code == 403
