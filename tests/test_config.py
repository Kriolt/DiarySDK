from pathlib import Path

import pytest

from diarysdk.server.config import ConfigError, Settings


def test_from_env_reads_prefixed_vars():
    env = {
        "DIARYSDK_KEYS_FILE": "/srv/keys/api-keys",
        "DIARYSDK_VERSION": "abc1234",
        "DIARYSDK_DNEVNIK_URL": "http://dnevnik.test",
        "DIARYSDK_RATE_PER_SECOND": "2.5",
        "DIARYSDK_RATE_BURST": "5",
        "DIARYSDK_PORT": "9000",
    }

    settings = Settings.from_env(env)

    assert settings.keys_file == Path("/srv/keys/api-keys")
    assert settings.version == "abc1234"
    assert settings.dnevnik_url == "http://dnevnik.test"
    assert settings.rate_per_second == 2.5
    assert settings.rate_burst == 5
    assert settings.port == 9000


def test_from_env_defaults_point_to_live_diary():
    settings = Settings.from_env({"DIARYSDK_KEYS_FILE": "keys"})

    assert settings.dnevnik_url == "https://authedu.mosreg.ru"
    # Наблюдение: все запросы family/mobile сервиса отвечают и здесь, теми же данными.
    assert settings.school_api_url == "https://authedu.mosreg.ru/api"
    assert settings.school_url == "https://myschool.mosreg.ru"
    # Вход через Госуслуги.
    assert settings.esia_url == "https://esia.gosuslugi.ru"
    assert settings.rate_per_second == 10
    assert settings.rate_burst == 30
    # По умолчанию слушаем только свой компьютер.
    assert settings.host == "127.0.0.1"


def test_from_env_requires_keys_file():
    with pytest.raises(ConfigError, match="DIARYSDK_KEYS_FILE"):
        Settings.from_env({})


def test_from_env_rejects_non_number():
    with pytest.raises(ConfigError, match="DIARYSDK_RATE_BURST"):
        Settings.from_env({"DIARYSDK_KEYS_FILE": "keys", "DIARYSDK_RATE_BURST": "много"})


def test_defaults_come_from_hosts_and_package_version():
    from diarysdk import Hosts, __version__

    settings = Settings.from_env({"DIARYSDK_KEYS_FILE": "keys"})
    hosts = Hosts()

    assert (settings.dnevnik_url, settings.school_api_url) == (hosts.dnevnik, hosts.school_api)
    assert (settings.school_url, settings.esia_url) == (hosts.school, hosts.esia)
    assert settings.version == __version__
