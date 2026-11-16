from datetime import UTC, datetime

import pytest

from diarysdk._jwt import InvalidToken, decode_payload, expires_at
from tests.tokens import _part, make_token


def test_decode_payload_reads_claims_without_signature_check():
    token = make_token(datetime(2026, 11, 1, 12, 0, tzinfo=UTC), sub="1000001")

    assert decode_payload(token) == {"sub": "1000001", "exp": 1793534400}


def test_expires_at_is_utc_datetime():
    token = make_token(datetime(2026, 11, 1, 12, 0, tzinfo=UTC))

    assert expires_at(token) == datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "abc",
        "a.b",
        "a.b.c.d",
        f"{_part({'alg': 'none'})}.!!!.c2ln",
        f"{_part({'alg': 'none'})}.{_part(b'not json')}.c2ln",
        f"{_part({'alg': 'none'})}.{_part([1, 2])}.c2ln",
    ],
)
def test_broken_token_is_invalid(token):
    with pytest.raises(InvalidToken):
        decode_payload(token)


@pytest.mark.parametrize(
    "token",
    [
        make_token(sub="1000001"),
        f"{_part({'alg': 'none'})}.{_part({'exp': 'завтра'})}.c2ln",
        f"{_part({'alg': 'none'})}.{_part({'exp': True})}.c2ln",
    ],
)
def test_token_without_numeric_exp_is_invalid(token):
    with pytest.raises(InvalidToken):
        expires_at(token)
