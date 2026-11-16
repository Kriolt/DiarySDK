"""Настройки сервиса из переменных окружения DIARYSDK_*."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path

from diarysdk import Hosts, __version__

PREFIX = "DIARYSDK_"
_HOSTS = Hosts()


class ConfigError(Exception):
    """Настройка не задана или не разобралась."""


@dataclass(frozen=True)
class Settings:
    keys_file: Path
    # Версия сборки; уходит в X-App-Version. По умолчанию — версия пакета.
    version: str = __version__
    # Хосты дневника. В тестах все три смотрят на подставной дневник.
    dnevnik_url: str = _HOSTS.dnevnik
    # family/mobile. Наблюдение: здесь отвечает то же, что на
    # api.myschool.mosreg.ru, — лишний хост не держим.
    school_api_url: str = _HOSTS.school_api
    school_url: str = _HOSTS.school
    # ЕСИА для входа через Госуслуги.
    esia_url: str = _HOSTS.esia
    rate_per_second: float = 10.0
    rate_burst: int = 30
    host: str = "127.0.0.1"
    port: int = 8000

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        values = {}
        for field in fields(cls):
            name = PREFIX + field.name.upper()
            raw = env.get(name)
            if raw is None:
                continue
            try:
                values[field.name] = _convert(field.type, raw)
            except ValueError as error:
                raise ConfigError(f"{name}: не разобралось значение {raw!r}") from error
        if "keys_file" not in values:
            raise ConfigError(f"{PREFIX}KEYS_FILE не задан: без файла ключей сервис не стартует")
        return cls(**values)


def _convert(kind, raw: str):
    if kind in (Path, "Path"):
        return Path(raw)
    if kind in (int, "int"):
        return int(raw)
    if kind in (float, "float"):
        return float(raw)
    return raw
