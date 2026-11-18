"""Заглушка типов `sync.pyi`: не отстаёт от генератора, аннотации разрешаются и совпадают
с async-классами."""

import importlib.util
import inspect
import re
import typing
from pathlib import Path

import pytest

import diarysdk
from diarysdk import Diary, Login, LoginFlow, Student, sync
from diarysdk.remote import RemoteDiary, RemoteLogin, RemoteLoginFlow, RemoteStudent

ROOT = Path(__file__).resolve().parent.parent
STUB = ROOT / "diarysdk" / "sync.pyi"


def _generator():
    spec = importlib.util.spec_from_file_location(
        "gen_sync_stub", ROOT / "scripts/gen_sync_stub.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def stub():
    """Заглушка как модуль: `from __future__` откладывает аннотации, как это делает проверяющий."""
    source = "from __future__ import annotations\n" + STUB.read_text(encoding="utf-8")
    namespace: dict = {"__name__": "sync_stub"}
    exec(compile(source, str(STUB), "exec"), namespace)  # noqa: S102 - наш же файл
    return namespace


def test_stub_is_up_to_date():
    assert STUB.read_text(encoding="utf-8") == _generator().render(), (
        "diarysdk/sync.pyi устарел: python scripts/gen_sync_stub.py"
    )


def test_package_is_typed():
    assert (ROOT / "diarysdk" / "py.typed").is_file()
    assert Path(diarysdk.__file__).with_name("py.typed").is_file()


def _shape(annotation) -> str:
    text = str(annotation)
    text = re.sub(r"diarysdk\.remote\.\w+\.Remote(\w+)", r"\1", text)
    text = re.sub(r"(?:diarysdk\.client|sync_stub)\.(\w+)", r"\1", text)
    return re.sub(r"\bRemote(Diary|Login|LoginFlow|Student)\b", r"\1", text)


def _signature(function):
    signature = inspect.signature(function, eval_str=True)
    return [
        (p.name, p.kind, p.default, _shape(p.annotation)) for p in signature.parameters.values()
    ], _shape(signature.return_annotation)


PAIRS = [
    ("Login", Login, RemoteLogin),
    ("LoginFlow", LoginFlow, RemoteLoginFlow),
    ("Student", Student, RemoteStudent),
]


@pytest.mark.parametrize(("name", "core", "remote"), PAIRS)
def test_stub_methods_match_async_classes(stub, name, core, remote):
    stubbed = stub[name]
    names = {n for n, _ in inspect.getmembers(stubbed, inspect.isfunction) if not n.startswith("_")}
    assert names == {n for n, _ in inspect.getmembers(core, inspect.isfunction) if n[0] != "_"}
    for n in sorted(names):
        for other in (core, remote):
            ours = _signature(getattr(stubbed, n))
            theirs = _signature(getattr(other, n))
            # `self` у обеих есть; async у них, но в аннотации это не видно.
            assert ours == theirs, (name, n)
    for prop in ("kind", "mfa", "captcha", "expires_at", "token"):
        if isinstance(inspect.getattr_static(core, prop, None), property):
            hints = typing.get_type_hints(getattr(stubbed, prop).fget, globalns=stub)
            assert hints["return"] is not None


@pytest.mark.parametrize(("name", "core"), [("Diary", Diary), ("RemoteDiary", RemoteDiary)])
def test_stub_diary_matches_async_class(stub, name, core):
    stubbed = stub[name]
    assert _signature(stubbed.__init__) == _signature(core.__init__)
    assert _signature(stubbed.student) == _signature(core.student)
    assert _signature(stubbed.parent) == _signature(core.parent)
    assert {n for n, _ in inspect.getmembers(stubbed, inspect.isfunction) if n[0] != "_"} == {
        "close",
        "student",
        "parent",
    }
    assert isinstance(stubbed.login, property)


def test_stub_declares_every_runtime_class(stub):
    for name in sync.__all__:
        assert name in stub
