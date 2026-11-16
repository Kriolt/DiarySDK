"""Чистота репозитория: общие правила на дереве и на синтетических образцах."""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_clean.py"
FORBIDDEN = ROOT / "docs" / "internal" / "forbidden.txt"

spec = importlib.util.spec_from_file_location("check_clean", SCRIPT)
check_clean = importlib.util.module_from_spec(spec)
sys.modules["check_clean"] = check_clean
spec.loader.exec_module(check_clean)

# Образцы собираются из частей, чтобы сам тест не срабатывал на правила.
HOME = "/ho" + "me/someone/project"
MAC_HOME = "/Us" + "ers/someone/project"
WIN_HOME = "C:" + "\\Us" + "ers\\someone"
FAKE_SIGNATURE = "c2lnbmF0dXJl"
JWT_HEAD = "eyJ" + "hbGciOiJSUzI1NiJ9"
JWT_BODY = "eyJ" + "zdWIiOiIxMDAwMDAxIn0"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=ROOT, capture_output=True, text=True
    )


def test_repository_is_clean():
    result = _run()

    assert result.stdout == ""
    assert result.returncode == 0


@pytest.mark.skipif(not FORBIDDEN.exists(), reason="локального списка нет")
def test_repository_is_clean_against_local_list():
    result = _run("--extra", str(FORBIDDEN))

    assert result.stdout == ""
    assert result.returncode == 0


@pytest.mark.parametrize("line", [HOME, MAC_HOME, WIN_HOME])
def test_home_paths_are_found(line):
    assert check_clean.generic_line_rules(f"путь {line}/x") == ["домашний путь"]


def test_plain_home_mention_is_not_a_path_with_user():
    assert check_clean.generic_line_rules("каталог /ho" + "me/ без имени") == []


def test_probe_file_names_are_found():
    assert check_clean.generic_name_rules("data/probe" + "_1.json") == ["файл probe*.json"]
    assert check_clean.generic_name_rules("data/probe.json")
    assert check_clean.generic_name_rules("data/marks.json") == []


def test_real_looking_jwt_is_found():
    assert check_clean.generic_line_rules(f"t = {JWT_HEAD}.{JWT_BODY}.abcdefghijk") == ["JWT"]


def test_only_fake_signature_allows_jwt():
    fake = f"{JWT_HEAD}.{JWT_BODY}.{FAKE_SIGNATURE}"
    marked = f"{JWT_HEAD}.{JWT_BODY}.abcdefghijk  # clean: allow-jwt"
    mixed = f"{fake} {JWT_HEAD}.{JWT_BODY}.abcdefghijk"

    assert check_clean.generic_line_rules(fake) == []
    assert check_clean.generic_line_rules(marked) == ["JWT"]
    assert check_clean.generic_line_rules(mixed) == ["JWT"]


def test_short_jwt_prefix_is_not_a_token():
    assert check_clean.generic_line_rules("eyJ.diary.token") == []


@pytest.mark.parametrize(
    "address",
    [
        "someone@" + "mail.example2.org",
        "a.b@" + "gmail.com",
        "x@" + "school.ru",
        "a@" + "example.attacker.ru",
        "a@" + "corp.example.ru",
        "a@" + "notexample.com",
    ],
)
def test_emails_are_found(address):
    assert check_clean.generic_line_rules(f"пишите {address}") == ["почтовый адрес"]


@pytest.mark.parametrize(
    "address",
    [
        "12345+name@users.noreply.github.com",
        "noreply@anthropic.com",
        "user@example.com",
        "user@example.test",
        "user@mail.test",
        "user@sub.example.org",
        "user@example.net",
        "user@host.invalid",
        "user@host.localhost",
        "user@host.example",
        "git+https://github.com/Org/Repo@v0.1.0",
    ],
)
def test_allowed_emails_pass(address):
    assert check_clean.generic_line_rules(f"пишите {address}") == []


def test_url_userinfo_is_not_an_email_but_path_address_is():
    assert check_clean.generic_line_rules("https://user@host.ru/path") == []
    assert check_clean.generic_line_rules("http://h/real@" + "mail.ru") == ["почтовый адрес"]


@pytest.mark.parametrize(
    "number",
    [
        "+7 " + "912 345-67-89",
        "+7(" + "912)3456789",
        "891" + "23456789",
        "8 (" + "912) 345 67 89",
        "+79" + "123456789",
    ],
)
def test_phones_are_found(number):
    assert check_clean.generic_line_rules(f"тел. {number}") == ["телефон"]


@pytest.mark.parametrize("number", ["+7 000 123-45-67", "8 (000) 345 67 89", "+7 912 000 00 00"])
def test_obvious_fake_phones_pass(number):
    assert check_clean.generic_line_rules(f"тел. {number}") == []


@pytest.mark.parametrize(
    "number", ["+7 900 " + "100 00 05", "8 495 " + "100 00 00", "+7 912 " + "345 00 00"]
)
def test_phones_with_some_zeros_are_found(number):
    assert check_clean.generic_line_rules(f"тел. {number}") == ["телефон"]


def test_bare_eleven_digits_not_starting_with_89_are_not_phones():
    assert check_clean.generic_line_rules("id 84951234567") == []
    assert check_clean.generic_line_rules("id 8912" + "1234567") == ["телефон"]


def test_masked_phone_and_long_numbers_pass():
    assert check_clean.generic_line_rules("+7 *** ***-**-12") == []
    assert check_clean.generic_line_rules("id 1234567890123") == []


def test_extra_list_reports_rule_line_not_text(tmp_path):
    extra = tmp_path / "extra.txt"
    extra.write_text("# комментарий\n\nsecretword\n(?-i:CaseOnly)\n", encoding="utf-8")
    rules = check_clean.load_extra(extra)

    found = check_clean.scan_text("f.txt", "ok\nSECRETWORD here\ncaseonly CaseOnly", rules)

    assert found == [
        "f.txt:2: правило 3 из дополнительного списка",
        "f.txt:3: правило 4 из дополнительного списка",
    ]
    assert not any("ecret" in line for line in found)
    assert check_clean.scan_text("f.txt", "caseonly", rules) == []


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Tester", "-c", "user.email=t@example.test", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_cli_scans_tracked_files_names_and_history(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "clean.txt").write_text("всё чисто\n", encoding="utf-8")
    (repo / "notes.txt").write_text(f"a\nпуть {HOME}/x\n", encoding="utf-8")
    (repo / ("probe" + "_x.json")).write_text("{}", encoding="utf-8")
    (repo / "untracked.txt").write_text(f"{HOME}/y\n", encoding="utf-8")
    (repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (repo / "ignored.txt").write_text(f"{HOME}/z\n", encoding="utf-8")
    (repo / "bin.dat").write_bytes(b"\0" + HOME.encode())
    _git(repo, "add", "clean.txt", "notes.txt", "probe_x.json", "bin.dat")
    _git(repo, "commit", "-q", "-m", "служебное слово hidden-term")
    extra = tmp_path / "extra.txt"
    extra.write_text("hidden-term\n", encoding="utf-8")

    assert check_clean.main([], root=repo) == 1
    tree = capsys.readouterr().out.splitlines()
    assert tree == [
        "notes.txt:2: домашний путь",
        "probe_x.json:0: имя файла: файл probe*.json",
        "untracked.txt:1: домашний путь",
    ]

    assert check_clean.main(["--extra", str(extra), "--history"], root=repo) == 1
    both = capsys.readouterr().out.splitlines()
    assert both[:3] == tree
    assert re.fullmatch(r"коммит [0-9a-f]+:5: правило 1 из дополнительного списка", both[3])
    assert "hidden-term" not in "".join(both)


def test_cli_exit_zero_on_clean_repo(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.txt").write_text("чисто\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "первый")

    assert check_clean.main(["--history"], root=repo) == 0
    assert capsys.readouterr().out == ""
