"""examples/*.py: импортируются без сети и не стартуют сами (bot_flow — в tests/remote)."""

import importlib.util
from pathlib import Path

import pytest

from diarysdk.models.homework import Homework
from diarysdk.models.school import School
from tests.fakes import FakeDiary, core_diary
from tests.tokens import valid_token

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"example_{name}", EXAMPLES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["bot_flow", "direct", "sync_remote"])
def test_example_imports_and_has_guarded_main(name):
    module = load(name)
    assert callable(module.main)
    assert 'if __name__ == "__main__"' in (EXAMPLES / f"{name}.py").read_text()


async def test_direct_example_reads_through_diary(capsys):
    fake = FakeDiary(
        school=School(name="Гимназия"),
        marks=[],
        homework=[Homework(id=5, is_done=False)],
    )
    async with core_diary(fake) as api:
        await load("direct").show(api, valid_token())
    out = capsys.readouterr().out
    assert "Гимназия" in out
    assert "не сделано" in out


async def test_direct_example_main_needs_token(monkeypatch):
    monkeypatch.delenv("DIARY_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        await load("direct").main()


def test_sync_example_main_needs_environment(monkeypatch):
    for name in ("DIARYSDK_URL", "DIARYSDK_KEY", "DIARY_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit):
        load("sync_remote").main()
