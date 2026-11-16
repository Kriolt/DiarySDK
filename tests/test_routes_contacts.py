import pytest
from httpx import ASGITransport, AsyncClient

from diarysdk.errors import NotFound, UnsupportedContact, UpstreamError
from diarysdk.server.app import create_app
from diarysdk.server.keys import hash_key
from tests.conftest import API_KEY, AUTH_HEADERS
from tests.fakes import core_diary

URL = "/v1/identity/contacts/2"
BODY = {"value": "new@example.test"}


@pytest.fixture
def keys_file(tmp_path):
    path = tmp_path / "api-keys"
    path.write_text(f"tests {hash_key(API_KEY)} write_profile\n")
    return path


@pytest.fixture
async def plain(tmp_path, fake_diary, today):
    """Ключ без write_profile."""
    from diarysdk.server.config import Settings

    path = tmp_path / "plain-keys"
    path.write_text(f"tests {hash_key(API_KEY)} login\n")
    app = create_app(Settings(keys_file=path, version="x"), diary=core_diary(fake_diary))
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers=AUTH_HEADERS
    ) as c:
        yield c


async def test_put_is_no_content_and_passes_id_and_value(api, fake_diary):
    fake_diary.answers["update_contact"] = None

    response = await api.put(URL, json=BODY)

    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["cache-control"] == "no-store"
    assert fake_diary.args["update_contact"][1:] == (2, "new@example.test")


async def test_without_write_profile_is_forbidden_before_any_diary_call(plain, fake_diary):
    response = await plain.put(URL, json=BODY)

    assert response.status_code == 403
    assert response.json()["error"] == "forbidden_scope"
    assert fake_diary.calls == []


async def test_forbidden_even_with_bad_body_or_no_body(plain, fake_diary):
    for kwargs in ({"json": {"is_default": True}}, {}):
        response = await plain.put(URL, **kwargs)
        assert response.status_code == 403
    assert fake_diary.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"value": None},
        {"value": "new@example.test", "is_default": True},
        {"is_default": True},
        {"value": "no-at-sign"},
        {"value": "a@b@c"},
        {"value": "a@@b"},
        {"value": "a b@c"},
    ],
)
async def test_bad_body_is_bad_request_without_diary_call(api, fake_diary, body):
    response = await api.put(URL, json=body)

    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
    assert fake_diary.calls == []


@pytest.mark.parametrize("contact_id", ["0", "-1", "abc"])
async def test_bad_id_is_bad_request_without_diary_call(api, fake_diary, contact_id):
    response = await api.put(f"/v1/identity/contacts/{contact_id}", json=BODY)

    assert response.status_code == 400
    assert fake_diary.calls == []


async def test_no_body_is_bad_request(api, fake_diary):
    response = await api.put(URL)

    assert response.status_code == 400
    assert fake_diary.calls == []


async def test_foreign_contact_is_not_found(api, fake_diary):
    fake_diary.answers["update_contact"] = NotFound()

    response = await api.put(URL, json=BODY)

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


async def test_not_email_is_unprocessable(api, fake_diary):
    fake_diary.answers["update_contact"] = UnsupportedContact()

    response = await api.put(URL, json=BODY)

    assert response.status_code == 422
    assert response.json()["error"] == "contact_not_email"


async def test_upstream_refusal_is_bad_gateway_with_status(api, fake_diary):
    fake_diary.answers["update_contact"] = UpstreamError(upstream_status=403)

    response = await api.put(URL, json=BODY)

    assert response.status_code == 502
    assert response.json()["error"] == "upstream_error"
    assert response.json()["upstream_status"] == 403
