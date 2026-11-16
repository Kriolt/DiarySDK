from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, StrictBool, model_validator

from diarysdk.models.common import Schema


class SettingsTheme(Schema):
    # Значения строками, как пришли. Известные из спецификации производителя:
    # type — dark, light; color_pattern — indigo, violet, pink.
    type: str | None = None
    is_automatic: bool | None = None
    color_pattern: str | None = None


class Settings(Schema):
    """Настройки приложения ученика (группа settings_group_v1).

    Не задавались — все поля null. Форма по спецификации производителя, живой
    ответ ещё не сверяли; справочника для estimation_type и goal нет.
    """

    goal: bool | None = None
    theme: SettingsTheme = Field(default_factory=SettingsTheme)
    # compact, full
    schedule_type: str | None = None
    estimation_type: str | None = None


class _Update(Schema):
    """Тело записи: лишние поля — ошибка, null — ошибка (поле либо есть, либо нет)."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _no_null(cls, data: Any) -> Any:
        if isinstance(data, dict) and any(value is None for value in data.values()):
            raise ValueError("null не принимается: поле либо передаётся, либо нет")
        return data


class SettingsThemeUpdate(_Update):
    type: Literal["dark", "light"] = Field(default=None)
    is_automatic: StrictBool = Field(default=None)
    color_pattern: Literal["indigo", "violet", "pink"] = Field(default=None)

    def changes(self) -> dict[str, Any]:
        return {f"theme.{name}": getattr(self, name) for name in self.model_fields_set}


class SettingsUpdate(_Update):
    """Что поменять в настройках. Хотя бы одно поле; null не принимается.

    Меняются только поля, у которых в дневнике уже есть значение: группы нет —
    `409 settings_missing`, поля нет — `409 setting_unset` (создать нечем, вернуть
    «не было» — тоже), текущее значение вне допустимых — `409 setting_unrestorable`
    (вернуть его назад было бы нечем). estimation_type не пишется.
    """

    goal: StrictBool = Field(default=None)
    theme: SettingsThemeUpdate = Field(default=None)
    schedule_type: Literal["compact", "full"] = Field(default=None)

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if not self.changes():
            raise ValueError("нужно хотя бы одно поле")
        return self

    def changes(self) -> dict[str, Any]:
        """Плоский вид: {"goal": True, "theme.type": "dark"} — только переданное."""
        result: dict[str, Any] = {}
        for name in self.model_fields_set:
            value = getattr(self, name)
            if isinstance(value, SettingsThemeUpdate):
                result.update(value.changes())
            else:
                result[name] = value
        return result
