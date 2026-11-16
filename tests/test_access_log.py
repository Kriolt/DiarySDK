import io
import json
import logging

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from diarysdk import _metrics
from diarysdk.server import logs
from diarysdk.server.app import create_app
from diarysdk.server.keys import hash_key
from tests.conftest import API_KEY, AUTH_HEADERS, TOKEN

router = APIRouter()


@router.get("/ping")
async def ping():
    return {"answer": "секретное-тело-ответа"}


@router.get("/two-diary-calls")
async def two_diary_calls():
    _metrics.count_diary_call()
    _metrics.count_diary_call()
    return {}


@pytest.fixture
def log_stream():
    stream = io.StringIO()
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    logs.configure(stream=stream)
    yield stream
    root.handlers, level = saved
    root.setLevel(level)


@pytest.fixture
async def client(settings, log_stream):
    app = create_app(settings, routers=[router])
    async with AsyncClient(transport=ASGITransport(app), base_url="http://t") as c:
        yield c


def request_records(stream):
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    return [line for line in lines if line["message"] == "request"]


async def test_one_json_line_per_request(client, log_stream):
    await client.get("/v1/ping", params={"from": "2026-09-01"}, headers=AUTH_HEADERS)

    [record] = request_records(log_stream)
    assert record["consumer"] == "tests"
    assert record["method"] == "GET"
    assert record["path"] == "/v1/ping"
    assert record["params"] == {"from": "2026-09-01"}
    assert record["status"] == 200
    assert record["duration_ms"] >= 0
    assert record["diary_calls"] == 0
    assert record["token"] == hash_key(TOKEN)[:12]
    assert record["time"].endswith("Z")


async def test_log_has_no_token_key_or_body(client, log_stream):
    await client.get("/v1/ping", headers=AUTH_HEADERS)

    text = log_stream.getvalue()
    assert TOKEN not in text
    assert API_KEY not in text
    assert "секретное-тело-ответа" not in text


async def test_values_of_unknown_params_are_hidden(client, log_stream):
    await client.get("/v1/ping", params={"token": "eyJ.секрет.подпись"}, headers=AUTH_HEADERS)

    [record] = request_records(log_stream)
    assert record["params"] == {"token": "***"}
    assert "секрет" not in log_stream.getvalue()


async def test_unmatched_path_is_not_logged_verbatim(client, log_stream):
    await client.get("/v1/eyJhbGciOiJSUzI1NiJ9-oops", headers=AUTH_HEADERS)

    [record] = request_records(log_stream)
    assert record["status"] == 404
    assert record["path"] is None
    assert "eyJhbGciOiJSUzI1NiJ9" not in log_stream.getvalue()


async def test_diary_calls_of_this_request_are_counted(client, log_stream):
    await client.get("/v1/two-diary-calls", headers=AUTH_HEADERS)

    [record] = request_records(log_stream)
    assert record["diary_calls"] == 2


async def test_v1_responses_are_no_store_even_on_error(client):
    ok = await client.get("/v1/ping", headers=AUTH_HEADERS)
    forbidden = await client.get("/v1/ping")

    assert ok.headers["Cache-Control"] == "no-store"
    assert forbidden.status_code == 403
    assert forbidden.headers["Cache-Control"] == "no-store"


def test_http_client_loggers_are_quiet(log_stream):
    # На INFO httpx пишет полный URL запроса, а в нём ID ученика и GUID.
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("httpcore.http11").getEffectiveLevel() == logging.WARNING


def test_exception_text_is_not_logged(log_stream):
    try:
        raise ValueError("значение-с-персональными-данными")
    except ValueError:
        logging.getLogger("diarysdk.test").exception("упало")

    [line] = log_stream.getvalue().splitlines()
    record = json.loads(line)
    assert record["error_type"] == "ValueError"
    assert "значение-с-персональными-данными" not in line


def test_uvicorn_color_message_is_dropped(log_stream):
    logging.getLogger("uvicorn.error").info(
        "Started", extra={"color_message": "Started \x1b[36m1\x1b[0m"}
    )

    record = json.loads(log_stream.getvalue().splitlines()[-1])
    assert record["message"] == "Started"
    assert "color_message" not in record


async def test_subject_param_is_logged(client, log_stream):
    await client.get("/v1/ping", params={"subject": "77"}, headers=AUTH_HEADERS)

    [record] = request_records(log_stream)
    assert record["params"] == {"subject": "77"}


async def test_flow_id_of_esia_login_is_hidden(client, log_stream):
    # flow_id — ручка начатого входа: в журнале ей не место, как и токену.
    flow_id = "Zx9-secret-flow-id_42"
    await client.post(f"/v1/auth/esia/{flow_id}/code", json={}, headers=AUTH_HEADERS)
    await client.delete(f"/v1/auth/esia/{flow_id}", headers=AUTH_HEADERS)

    records = request_records(log_stream)
    assert [r["path"] for r in records] == ["/v1/auth/esia/***/code", "/v1/auth/esia/***"]
    assert flow_id not in log_stream.getvalue()
