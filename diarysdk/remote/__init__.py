"""Удалённый клиент сервера: тот же интерфейс, что у ядра (`Diary`)."""

from diarysdk.remote.auth import RemoteLogin, RemoteLoginFlow
from diarysdk.remote.client import RemoteDiary
from diarysdk.remote.student import RemoteStudent

__all__ = ["RemoteDiary", "RemoteLogin", "RemoteLoginFlow", "RemoteStudent"]
