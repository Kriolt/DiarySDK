import pytest

from diarysdk.server import keys
from diarysdk.server.keys import hash_key


def test_new_prints_hash_line_to_stdout_and_key_to_stderr(capsys):
    code = keys.main(["new", "bot"])

    out, err = capsys.readouterr()
    assert code == 0
    consumer, digest = out.split()
    key = err.strip().splitlines()[-1]
    assert consumer == "bot"
    assert hash_key(key) == digest
    assert len(key) >= 43  # 32 байта в base64url


def test_each_new_key_is_different(capsys):
    keys.main(["new", "bot"])
    keys.main(["new", "bot"])

    out, _ = capsys.readouterr()
    first, second = out.splitlines()
    assert first != second


def test_gh_repo_option_is_gone(capsys):
    with pytest.raises(SystemExit) as exit_info:
        keys.main(["new", "bot", "--gh-repo", "owner/repo"])

    assert exit_info.value.code == 2


def test_bad_consumer_name_is_usage_error(capsys):
    with pytest.raises(SystemExit) as exit_info:
        keys.main(["new", "бот с пробелом"])

    assert exit_info.value.code == 2


def test_new_with_scope_appends_scope_to_line(capsys):
    code = keys.main(["new", "bot", "--scope", "login"])

    out, _ = capsys.readouterr()
    assert code == 0
    consumer, _digest, scope = out.split()
    assert (consumer, scope) == ("bot", "login")


def test_new_rejects_unknown_scope(capsys):
    with pytest.raises(SystemExit):
        keys.main(["new", "bot", "--scope", "admin"])


def test_new_accepts_several_scopes_in_order_without_repeats(capsys):
    code = keys.main(
        ["new", "bot", "--scope", "login", "--scope", "write_profile", "--scope", "login"]
    )

    out, _ = capsys.readouterr()
    assert code == 0
    assert out.split()[2] == "login,write_profile"


def test_new_write_profile_alone(capsys):
    keys.main(["new", "bot", "--scope", "write_profile"])

    out, _ = capsys.readouterr()
    assert out.split()[2] == "write_profile"
