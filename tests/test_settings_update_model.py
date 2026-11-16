import pytest
from pydantic import ValidationError

from diarysdk.models.settings import SettingsThemeUpdate, SettingsUpdate


def test_changes_lists_only_given_fields():
    update = SettingsUpdate.model_validate(
        {"goal": False, "theme": {"type": "dark", "is_automatic": False}}
    )

    assert update.changes() == {"goal": False, "theme.type": "dark", "theme.is_automatic": False}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"theme": {}},
        {"goal": None},
        {"schedule_type": None},
        {"theme": None},
        {"theme": {"type": None}},
        {"goal": True, "estimation_type": "five"},
        {"goal": True, "extra": 1},
        {"theme": {"type": "blue"}},
        {"theme": {"color_pattern": "red"}},
        {"schedule_type": "wide"},
        {"theme": {"type": "dark", "other": 1}},
        {"goal": "yes"},
        {"goal": 1},
        {"theme": {"is_automatic": "false"}},
    ],
)
def test_bad_bodies_are_rejected(body):
    with pytest.raises(ValidationError):
        SettingsUpdate.model_validate(body)


def test_null_is_rejected_in_constructor_too():
    with pytest.raises(ValidationError):
        SettingsUpdate(goal=None)
    with pytest.raises(ValidationError):
        SettingsThemeUpdate(type=None)


def test_theme_object_with_fields():
    assert SettingsUpdate(theme=SettingsThemeUpdate(color_pattern="violet")).changes() == {
        "theme.color_pattern": "violet"
    }
