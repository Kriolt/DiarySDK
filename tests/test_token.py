"""Token: срок из JWT без исключений и без секретов в repr."""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from diarysdk import Token
from tests.tokens import make_token, valid_token


def _jwt(payload) -> str:
    def part(data) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'none'})}.{part(payload)}.c2ln"


def test_token_knows_expiry():
    exp = datetime.now(UTC) + timedelta(minutes=30)
    token = Token(make_token(exp))

    assert abs(token.expires_at - exp) < timedelta(seconds=1)
    assert timedelta(minutes=29) < token.expires_in() <= timedelta(minutes=30)
    assert not token.is_expiring(timedelta(minutes=5))
    assert token.is_expiring(timedelta(hours=1))


def test_expired_token_is_expiring():
    assert Token(make_token(datetime.now(UTC) - timedelta(seconds=1))).is_expiring(timedelta(0))


def test_token_without_exp():
    token = Token(make_token(None, sub="1"))

    assert token.expires_at is None
    assert token.expires_in() is None
    assert token.is_expiring(timedelta(days=3650)) is False


@pytest.mark.parametrize(
    "garbage",
    [
        "",
        "abc",
        "a.b.c",
        "a.b",
        "..",
        _jwt(["не объект"]),
        _jwt({"exp": "1893456000"}),
        _jwt({"exp": True}),
        _jwt({"exp": 10**30}),
        "e30.!!!.c2ln",
    ],
)
def test_token_garbage(garbage):
    token = Token(garbage)

    assert token.expires_at is None
    assert token.expires_in() is None
    assert token.value == garbage
    assert "sha256=" in repr(token)


def test_repr_is_expiry_and_hash_prefix_only():
    value = valid_token()
    token = Token(value)

    tag = hashlib.sha256(value.encode()).hexdigest()[:6]
    for text in (repr(token), str(token), f"{token}", repr([token])):
        assert f"sha256={tag}" in text
        assert token.expires_at.isoformat() in text
        assert value not in text
        assert value.split(".")[1] not in text


def test_naive_expiry_is_utc():
    token = Token(valid_token(), datetime(2030, 1, 1))  # noqa: DTZ001 - проверяем наивное время

    assert token.expires_at.tzinfo is UTC


def test_equality_by_value():
    value = valid_token()

    assert Token(value) == Token(value)
    assert Token(value) != value


def test_token_subject_and_roles_from_payload():
    token = Token(valid_token(rol="student, parent"))

    assert token.subject_id == "1000001"
    assert token.roles == ["student", "parent"]
    assert Token(valid_token(roles=["a", 7, None])).roles == ["a", "7"]
    assert Token(_jwt({"sub": True, "exp": 1})).subject_id is None


def test_token_subject_and_roles_of_garbage_are_empty():
    token = Token("не-jwt")

    assert token.subject_id is None
    assert token.roles == []


def test_ensure_usable():
    from diarysdk import errors

    Token(valid_token()).ensure_usable()
    with pytest.raises(errors.TokenExpired):
        Token(make_token(datetime.now(UTC) - timedelta(seconds=1))).ensure_usable()
    with pytest.raises(errors.TokenInvalid):
        Token(make_token(None, sub="1")).ensure_usable()
    with pytest.raises(errors.TokenInvalid):
        Token("не-jwt").ensure_usable()
