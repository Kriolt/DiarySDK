"""Документация каждого открытого метода: текст протокола у ядра, remote и sync."""

import inspect
import typing

import pytest

from diarysdk import _protocols as protocols
from diarysdk import client, sync
from diarysdk.remote import RemoteDiary, RemoteLogin, RemoteLoginFlow, RemoteParent, RemoteStudent

PROTOCOLS = [
    protocols.DiaryLike,
    protocols.LoginLike,
    protocols.LoginFlowLike,
    protocols.StudentLike,
    protocols.ParentLike,
]
IMPLEMENTATIONS = {
    protocols.DiaryLike: [client.Diary, RemoteDiary, sync.Diary, sync.RemoteDiary],
    protocols.LoginLike: [client.Login, RemoteLogin, sync.Login],
    protocols.LoginFlowLike: [client.LoginFlow, RemoteLoginFlow, sync.LoginFlow],
    protocols.StudentLike: [client.Student, RemoteStudent, sync.Student],
    protocols.ParentLike: [client.Parent, RemoteParent, sync.Parent],
}


def _members(protocol):
    return sorted(typing.get_protocol_members(protocol))


def _doc(owner, name):
    raw = inspect.getattr_static(owner, name, None)
    if isinstance(raw, property):
        return inspect.cleandoc(raw.__doc__ or "")
    return inspect.getdoc(raw) if raw is not None else None


@pytest.mark.parametrize("protocol", PROTOCOLS, ids=lambda p: p.__name__)
def test_every_protocol_member_is_documented(protocol):
    assert protocol.__doc__
    for name in _members(protocol):
        doc = _doc(protocol, name)
        assert doc, f"{protocol.__name__}.{name}: нет документации"
        function = inspect.getattr_static(protocol, name)
        if callable(function) and not isinstance(function, property):
            params = [p for p in inspect.signature(function).parameters if p not in ("self", "exc")]
            if params:
                assert "Parameters\n----------" in doc, f"{protocol.__name__}.{name}"


@pytest.mark.parametrize(
    ("protocol", "owner"),
    [(p, c) for p, owners in IMPLEMENTATIONS.items() for c in owners],
    ids=lambda x: x.__qualname__ if hasattr(x, "__qualname__") else str(x),
)
def test_implementations_carry_protocol_docs(protocol, owner):
    assert owner.__doc__
    for name in _members(protocol):
        if inspect.getattr_static(owner, name, None) is None:
            continue  # атрибут экземпляра (login), а не член класса
        if owner in (sync.Diary, sync.RemoteDiary) and name in (
            "aclose",
            "__aenter__",
            "__aexit__",
        ):
            continue  # у синхронного входа их нет: close и with
        assert _doc(owner, name) == _doc(protocol, name), f"{owner.__qualname__}.{name}"


def test_every_public_method_of_public_classes_is_documented():
    import diarysdk
    import diarysdk.remote

    missing = []
    for module in (diarysdk, diarysdk.remote, sync):
        for name in module.__all__:
            owner = getattr(module, name)
            if not inspect.isclass(owner) or issubclass(owner, BaseException):
                continue
            if owner.__module__.startswith("diarysdk.models"):
                continue  # модели — данные: поля описаны в справочнике
            for member, value in vars(owner).items():
                if member.startswith("_") or not (callable(value) or isinstance(value, property)):
                    continue
                doc = value.__doc__ if isinstance(value, property) else inspect.getdoc(value)
                if not doc:
                    missing.append(f"{owner.__qualname__}.{member}")
    assert missing == []
