import pytest
from pydantic import ValidationError

from diarysdk.models.identity import ContactUpdate


@pytest.mark.parametrize("value", ["a@b", "name@example.test", "я@пример.рф", "a" * 253 + "@b"[:2]])
def test_valid(value):
    assert ContactUpdate(value=value).value == value


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"value": None},
        {"value": 5},
        {"value": ""},
        {"value": "@"},
        {"value": "a@"},
        {"value": "@b"},
        {"value": "ab"},
        {"value": "a@@b"},
        {"value": "a@b@c"},
        {"value": "a b@c"},
        {"value": "a@b\n"},
        {"value": "a@b\x00"},
        {"value": " a@b"},
        {"value": "a" * 254 + "@b"},
        {"value": "a@b", "is_default": True},
        {"value": "a@b", "extra": 1},
    ],
)
def test_invalid(body):
    with pytest.raises(ValidationError):
        ContactUpdate(**body)
