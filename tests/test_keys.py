import logging
import os

import pytest

from diarysdk.server.keys import KeyFileError, KeyStore, hash_key


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def rewrite(path, text):
    """Переписать файл и сдвинуть mtime: в тестах всё происходит в одну наносекунду."""
    old = path.stat().st_mtime_ns
    path.write_text(text)
    os.utime(path, ns=(old + 1_000_000_000, old + 1_000_000_000))


def name_of(consumer):
    return consumer.name if consumer else None


def test_hash_key_is_sha256_hex():
    assert hash_key("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_known_key_maps_to_consumer(tmp_path):
    path = tmp_path / "api-keys"
    path.write_text(f"bot {hash_key('k1')}\n")

    store = KeyStore(path)

    assert name_of(store.consumer_for("k1")) == "bot"
    assert name_of(store.consumer_for("k2")) is None
    assert name_of(store.consumer_for("")) is None


def test_consumer_may_have_two_keys_for_rotation(tmp_path):
    path = tmp_path / "api-keys"
    path.write_text(
        f"# бот меняет ключ\nbot {hash_key('old')}\n\nbot {hash_key('new')}\nsite {hash_key('s')}\n"
    )

    store = KeyStore(path)

    assert name_of(store.consumer_for("old")) == "bot"
    assert name_of(store.consumer_for("new")) == "bot"
    assert name_of(store.consumer_for("s")) == "site"


def test_removed_key_stops_working_after_check_interval(tmp_path):
    path = tmp_path / "api-keys"
    path.write_text(f"bot {hash_key('k1')}\n")
    clock = FakeClock()
    store = KeyStore(path, check_interval=10, clock=clock)
    assert name_of(store.consumer_for("k1")) == "bot"

    rewrite(path, f"site {hash_key('k2')}\n")
    clock.now = 5
    assert name_of(store.consumer_for("k1")) == "bot"

    clock.now = 11
    assert name_of(store.consumer_for("k1")) is None
    assert name_of(store.consumer_for("k2")) == "site"


def test_bad_line_is_skipped_and_logged_by_number_only(tmp_path, caplog):
    path = tmp_path / "api-keys"
    path.write_text(
        f"bot {hash_key('k1')}\nэто-не-строка-ключа\nsite не-хэш\nsite {hash_key('k3')}\n"
    )

    with caplog.at_level(logging.WARNING):
        store = KeyStore(path)

    assert name_of(store.consumer_for("k1")) == "bot"
    assert name_of(store.consumer_for("k3")) == "site"
    assert "2" in caplog.text and "3" in caplog.text
    assert "это-не-строка-ключа" not in caplog.text
    assert "не-хэш" not in caplog.text


def test_missing_file_at_start_raises(tmp_path):
    with pytest.raises(KeyFileError):
        KeyStore(tmp_path / "nope")


def test_unreadable_file_on_reload_keeps_previous_keys(tmp_path):
    path = tmp_path / "api-keys"
    path.write_text(f"bot {hash_key('k1')}\n")
    clock = FakeClock()
    store = KeyStore(path, check_interval=10, clock=clock)

    path.unlink()
    clock.now = 11

    assert name_of(store.consumer_for("k1")) == "bot"


def test_third_field_gives_scopes_of_that_line(tmp_path):
    path = tmp_path / "api-keys"
    path.write_text(f"bot {hash_key('k1')} login,future\nbot {hash_key('k2')}\n")

    store = KeyStore(path)

    assert store.consumer_for("k1").scopes == frozenset({"login", "future"})
    assert store.consumer_for("k2").scopes == frozenset()


def test_scopes_belong_to_matched_line_not_consumer_name(tmp_path):
    path = tmp_path / "api-keys"
    path.write_text(f"bot {hash_key('old')}\nbot {hash_key('new')} login\n")

    store = KeyStore(path)

    assert store.consumer_for("old").scopes == frozenset()
    assert store.consumer_for("new").scopes == frozenset({"login"})


def test_malformed_scope_field_skips_line(tmp_path):
    path = tmp_path / "api-keys"
    path.write_text(f"bot {hash_key('k1')} login,,x\nbot {hash_key('k2')} a b\n")

    store = KeyStore(path)

    assert store.consumer_for("k1") is None
    assert store.consumer_for("k2") is None


def test_line_with_login_and_write_profile_is_read(tmp_path):
    path = tmp_path / "keys"
    path.write_text(f"bot {hash_key('k1')} login,write_profile\nold {hash_key('k2')}\n")
    store = KeyStore(path)

    assert store.consumer_for("k1").scopes == frozenset({"login", "write_profile"})
    assert store.consumer_for("k2").scopes == frozenset()
