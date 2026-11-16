import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from diarysdk.errors import RateLimited, UpstreamError
from diarysdk.server.app import create_app
from tests.conftest import AUTH_HEADERS

router = APIRouter()


@router.get("/upstream")
async def upstream():
    raise UpstreamError("Дневник ответил ошибкой", upstream_status=500)


@router.get("/limited")
async def limited():
    raise RateLimited("Слишком часто", retry_after=3)


@router.get("/typed")
async def typed(n: int):
    return {"n": n}


@router.get("/crash")
async def crash():
    raise RuntimeError("секрет-123 из внутренностей")


@pytest.fixture
async def client(settings):
    app = create_app(settings, routers=[router])
    transport = ASGITransport(app, raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport, base_url="http://diarysdk.test", headers=AUTH_HEADERS
    ) as c:
        yield c


async def test_unknown_path_is_not_found(client):
    response = await client.get("/nope")

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
    assert response.json()["message"]


async def test_wrong_method_is_method_not_allowed(client):
    response = await client.post("/healthz")

    assert response.status_code == 405
    assert response.json()["error"] == "method_not_allowed"


async def test_error_keeps_code_and_extra_fields(client):
    response = await client.get("/v1/upstream")

    assert response.status_code == 502
    assert response.json() == {
        "error": "upstream_error",
        "message": "Дневник ответил ошибкой",
        "upstream_status": 500,
    }


async def test_error_keeps_headers(client):
    response = await client.get("/v1/limited")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "3"


async def test_validation_error_becomes_bad_request(client):
    response = await client.get("/v1/typed", params={"n": "abc"})

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert "abc" not in response.json()["message"]


async def test_unhandled_exception_hides_details(client):
    response = await client.get("/v1/crash")

    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert "секрет-123" not in response.text


async def test_unhandled_exception_is_no_store_too(client):
    response = await client.get("/v1/crash")

    assert response.status_code == 500
    assert response.headers.get("Cache-Control") == "no-store"
