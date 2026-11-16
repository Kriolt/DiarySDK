"""Правка контакта: прочитать карточку, найти свой контакт, записать с новым адресом.

Тело PUT — ровно {id, person_id, type_id, data, default}: проверка, тип и
неизвестные поля контакта не отправляются.
"""

import copy

import pytest

from diarysdk._gateway import DiaryGateway
from diarysdk.errors import NotFound, UnsupportedContact, UpstreamError
from tests.fakes import CTX, GUID, HOSTS, FakeTransport, core_diary, fixture
from tests.tokens import valid_token

CARD = f"/api/persondata/v1/persons/{GUID}"
PUT = f"{CARD}/contacts/2"
NEW = "new.address@example.test"
EMAIL = {
    "id": 2,
    "person_id": GUID,
    "type_id": 7,
    "type": {"id": 7, "name": "Электронная почта"},
    "data": "old@example.test",
    "default": False,
    "validation_state_id": 3,
    "validated_at": "2026-01-01",
    "future_field": {"x": 1},
}


def card(*extra):
    data = fixture("person_data.json")
    data["contacts"] = [*data["contacts"], *extra]
    return data


@pytest.fixture
def fake():
    fake = FakeTransport()
    fake.add(CARD, card(copy.deepcopy(EMAIL)))
    fake.add(f"PUT {PUT}", b"")
    return fake


@pytest.fixture
def gateway(fake):
    return DiaryGateway(fake, HOSTS)


def puts(fake):
    return [s for s in fake.sent if s.method == "PUT"]


async def test_put_body_is_exactly_the_five_app_fields(gateway, fake):
    assert await gateway.update_contact(CTX, 2, NEW) is None

    [put] = puts(fake)
    # В прочитанном контакте есть type, validation_state_id, validated_at и
    # неизвестное поле: назад уходят только пять полей приложения.
    assert put.json == {
        "id": 2,
        "person_id": GUID,
        "type_id": 7,
        "data": NEW,
        "default": False,
    }
    assert set(put.json) == {"id", "person_id", "type_id", "data", "default"}
    assert put.url == f"https://dnevnik.test{PUT}"
    assert put.header("authorization") == f"Bearer {CTX.token}"
    assert put.header("x-mes-subsystem") == "familymp"
    assert put.header("client-type") == "diary-mobile"
    assert put.header("profile-id") == "7001"
    assert put.call == "contact.put"


async def test_unknown_contact_is_not_found_without_put(gateway, fake):
    with pytest.raises(NotFound):
        await gateway.update_contact(CTX, 999, NEW)

    assert puts(fake) == []


async def test_phone_is_not_email_without_put(gateway, fake):
    # Контакт 1 из фикстуры - телефон.
    with pytest.raises(UnsupportedContact):
        await gateway.update_contact(CTX, 1, NEW)

    assert puts(fake) == []


@pytest.mark.parametrize(
    ("data", "type_name"),
    [
        ("+7 000 000-00-02", "Электронная почта"),
        ("a@b.test", "Мобильный телефон"),
        ("a@b.test", "Phone"),
        (None, "Электронная почта"),
        # Мессенджер: «@» есть, но перезаписать его почтовым правилом нельзя
        # (ContactUpdate не принимает пустую локальную часть) — вернуть нечем.
        ("@handle", "Telegram"),
        ("a@@b.test", "Электронная почта"),
        ("a b@c.test", "Электронная почта"),
        ("a@", "Электронная почта"),
    ],
)
async def test_not_email_by_value_or_by_type_name(gateway, fake, data, type_name):
    contact = copy.deepcopy(EMAIL)
    contact["data"] = data
    contact["type"] = {"id": 7, "name": type_name}
    fake.add(CARD, card(contact))

    with pytest.raises(UnsupportedContact):
        await gateway.update_contact(CTX, 2, NEW)

    assert puts(fake) == []


async def test_card_not_readable_is_not_a_write(gateway, fake):
    fake.add(CARD, b"", status=404)

    with pytest.raises(NotFound):
        await gateway.update_contact(CTX, 2, NEW)

    assert puts(fake) == []


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_refusal_on_put_is_upstream_error_with_status(gateway, fake, status):
    fake.add(f"PUT {PUT}", b"", status=status)

    with pytest.raises(UpstreamError) as caught:
        await gateway.update_contact(CTX, 2, NEW)

    assert caught.value.upstream_status == status


async def test_success_false_on_put_is_upstream_error(gateway, fake):
    fake.add(f"PUT {PUT}", {"success": False})

    with pytest.raises(UpstreamError):
        await gateway.update_contact(CTX, 2, NEW)


async def test_403_on_put_keeps_token_context_in_cache(gateway, fake):
    fake.add("/api/family/web/v1/profile", fixture("profile.json"))
    fake.add(f"PUT {PUT}", b"", status=403)
    diary = core_diary(gateway)
    token = valid_token()

    for _ in range(2):
        with pytest.raises(UpstreamError) as caught:
            await diary.student(token).update_contact(2, NEW)
        assert caught.value.upstream_status == 403

    profiles = [s for s in fake.sent if s.url.endswith("/api/family/web/v1/profile")]
    assert len(profiles) == 1


async def test_403_on_card_read_still_evicts_context(gateway, fake):
    fake.add("/api/family/web/v1/profile", fixture("profile.json"))
    fake.add(CARD, b"", status=403)
    diary = core_diary(gateway)

    for _ in range(2):
        with pytest.raises(Exception) as caught:
            await diary.student(valid_token()).update_contact(2, NEW)
        assert type(caught.value).__name__ == "TokenInvalid"

    profiles = [s for s in fake.sent if s.url.endswith("/api/family/web/v1/profile")]
    assert len(profiles) == 2
