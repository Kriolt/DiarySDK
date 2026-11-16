"""/v1/settings из сырой группы settings_group_v1 (raw.user_settings).

Группы нет — все поля null. Значения как пришли; чужое по форме (скажем, goal
строкой) — UpstreamFormat, без значений.
"""

import copy
from typing import Any

from pydantic import ValidationError

from diarysdk._wire.mobile import UserSettings
from diarysdk.errors import SettingNotSet, SettingUnrestorable, UpstreamFormat
from diarysdk.models.settings import Settings, SettingsTheme, SettingsThemeUpdate, SettingsUpdate


def settings(data: dict[str, Any] | None) -> Settings:
    try:
        parsed = UserSettings.model_validate(data or {})
    except ValidationError as error:
        raise UpstreamFormat.from_validation(error) from None
    theme = parsed.theme
    return Settings(
        goal=parsed.goal,
        theme=SettingsTheme(
            type=theme.type if theme else None,
            is_automatic=theme.is_automatic if theme else None,
            color_pattern=theme.color_pattern if theme else None,
        ),
        schedule_type=parsed.schedule_type,
        estimation_type=parsed.estimation_type,
    )


def merged(group: dict[str, Any], update: SettingsUpdate) -> dict[str, Any]:
    """Прочитанная группа с заменёнными полями из запроса; остальное — как было,
    в том числе неизвестные нам поля. Поле, у которого сейчас нет значения
    (нет ключа или null), записать нельзя — SettingNotSet, пока ничего не
    изменено. Ложь (False, 0, "") — значение. Текущее значение, которое сервис
    сам не смог бы записать (вне enum или не того типа), — SettingUnrestorable:
    перезапись не вернуть."""
    result = copy.deepcopy(group)
    changes = update.changes()
    for path in changes:
        holder = result
        *parents, name = path.split(".")
        for parent in parents:
            holder = holder.get(parent)
            if not isinstance(holder, dict):
                raise SettingNotSet(field=path)
        if holder.get(name) is None:
            raise SettingNotSet(field=path)
        if not _writable(path, holder[name]):
            raise SettingUnrestorable(field=path)
    for path, value in changes.items():
        holder = result
        *parents, name = path.split(".")
        for parent in parents:
            holder = holder[parent]
        holder[name] = value
    return result


def _writable(path: str, value: Any) -> bool:
    """Приняла бы схема записи это значение в это поле."""
    *parents, name = path.split(".")
    model = SettingsThemeUpdate if parents else SettingsUpdate
    try:
        model.model_validate({name: value})
    except ValidationError:
        return False
    return True
