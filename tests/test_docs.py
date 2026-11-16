"""Примеры из README и справочник: примеры исполняются, имена API описаны.

Исполняется каждый блок ```python, перед которым стоит строка `<!-- test -->`.
Сети нет: прямой клиент работает на подставном дневнике, удалённый ходит в
настоящее приложение через ASGI-транспорт, синхронный — тем же способом.
"""

import builtins
import re
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

import diarysdk
import diarysdk.remote
import diarysdk.sync
from diarysdk._port import EsiaStep
from diarysdk.models.common import Subject
from diarysdk.models.homework import Homework
from diarysdk.models.marks import Mark
from diarysdk.models.school import School
from diarysdk.server.app import create_app
from diarysdk.server.config import Settings
from diarysdk.server.keys import hash_key
from tests.fakes import core_diary
from tests.remote.esia import FRESH, IMAGE, SMS, EsiaDiary, Session
from tests.tokens import valid_token

ROOT = Path(__file__).resolve().parents[1]
MARKER = "<!-- test -->"
# Ключ и адрес из примеров README.
DOC_KEY = "my-api-key"
DOC_URL = "https://diarysdk.example"
BLOCK = re.compile(rf"^{re.escape(MARKER)}\n```python\n(.*?)^```$", re.MULTILINE | re.DOTALL)


def runnable_blocks(path: Path) -> list[str]:
    return BLOCK.findall(path.read_text())


README_BLOCKS = runnable_blocks(ROOT / "README.md")


def test_readme_has_runnable_examples():
    # Разметка сломалась бы молча: ни один пример не исполнялся бы.
    assert len(README_BLOCKS) >= 8
    text = (ROOT / "README.md").read_text()
    assert text.count(MARKER) == len(README_BLOCKS)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Подставной дневник, сервис над ним и подмена классов клиента в примерах."""
    fake = EsiaDiary(
        esia_start=(Session("captcha"), EsiaStep(captcha=IMAGE)),
        esia_captcha=EsiaStep(mfa=SMS),
        esia_captcha_renew=EsiaStep(captcha=FRESH),
        esia_code=valid_token(),
        password_login=valid_token(),
        school=School(name="Гимназия"),
        marks=[Mark(id=1, subject=Subject(name="Алгебра"), value="9")],
        homework=[Homework(id=5, is_done=False)],
        set_homework_done=None,
    )
    keys = tmp_path / "api-keys"
    keys.write_text(f"docs {hash_key(DOC_KEY)} login,write_profile\n")
    app = create_app(Settings(keys_file=keys), diary=core_diary(fake))

    real_remote = diarysdk.remote.RemoteDiary

    def remote(base_url, api_key, **options):
        assert base_url == DOC_URL
        http = httpx.AsyncClient(transport=ASGITransport(app))
        return real_remote(base_url, api_key, http=http, **options)

    def direct(**options):
        return core_diary(fake, **options)

    monkeypatch.setattr(diarysdk, "Diary", direct)
    monkeypatch.setattr(diarysdk.remote, "RemoteDiary", remote)
    monkeypatch.setattr(diarysdk.sync.RemoteDiary, "_async_class", staticmethod(remote))
    monkeypatch.setattr(diarysdk.sync.Diary, "_async_class", staticmethod(direct))
    monkeypatch.setenv("DIARY_TOKEN", valid_token())
    answers = {"Капча": "ответ", "Код": "246813"}
    monkeypatch.setattr(builtins, "input", lambda prompt="": answers[prompt.rstrip(": ")])
    return fake


@pytest.mark.parametrize("source", README_BLOCKS, ids=lambda s: s.strip().splitlines()[0][:40])
def test_readme_example_runs(source, world, capsys):
    exec(compile(source, "README.md", "exec"), {"__name__": "__main__"})  # noqa: S102
    assert capsys.readouterr().out


def test_reference_mentions_every_public_name():
    text = (ROOT / "docs" / "reference.md").read_text()
    missing = [name for name in diarysdk.__all__ if not re.search(rf"\b{name}\b", text)]
    assert missing == []
