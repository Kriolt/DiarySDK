import pytest

from diarysdk._mapping.settings import settings
from diarysdk.errors import UpstreamFormat
from tests.fakes import fixture


def mapped(data):
    return settings(data).model_dump(mode="json")


def test_fixture_with_literal_values_goal_false_is_a_value():
    assert mapped(fixture("user_settings.json")) == {
        "goal": False,
        "theme": {"type": "dark", "is_automatic": False, "color_pattern": "indigo"},
        "schedule_type": "compact",
        "estimation_type": "five",
    }


@pytest.mark.parametrize("data", [None, {}, {"theme": None}])
def test_missing_group_is_all_null(data):
    assert mapped(data) == {
        "goal": None,
        "theme": {"type": None, "is_automatic": None, "color_pattern": None},
        "schedule_type": None,
        "estimation_type": None,
    }


def test_wrong_shape_is_format_error_without_values():
    with pytest.raises(UpstreamFormat) as error:
        settings({"goal": "секрет-значение"})

    assert "секрет-значение" not in str(error.value)
