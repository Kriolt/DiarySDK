"""Синхронные обёртки: `sync.Diary` и `sync.RemoteDiary`.

Каждая оборачивает одноимённый async-класс и ведёт его в своём потоке с циклом
событий (`_Portal`): по одному потоку на экземпляр. Классы обёрток строятся по
протоколам из `_protocols`: каждый async-метод становится обычным методом с той
же сигнатурой, а `Login`, `LoginFlow` и `Student`, которые он возвращает,
оборачиваются так же. Исключения доходят без изменений.

Вызов блокирует вызывающий поток. Из работающего цикла событий (async-функция,
Jupyter) он тоже допустим, но блокирует и этот цикл на время вызова: там
пользуйтесь async-классами.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import typing
from collections.abc import Callable, Coroutine
from typing import Any, Self

from diarysdk import _protocols as protocols
from diarysdk.client import Diary as _AsyncDiary
from diarysdk.client import Login as _AsyncLogin
from diarysdk.client import LoginFlow as _AsyncLoginFlow
from diarysdk.client import Parent as _AsyncParent
from diarysdk.client import Student as _AsyncStudent
from diarysdk.errors import BadCaptcha, BadCode
from diarysdk.remote import RemoteDiary as _AsyncRemoteDiary
from diarysdk.remote import RemoteLogin as _AsyncRemoteLogin
from diarysdk.remote import RemoteLoginFlow as _AsyncRemoteLoginFlow
from diarysdk.remote import RemoteParent as _AsyncRemoteParent
from diarysdk.remote import RemoteStudent as _AsyncRemoteStudent

__all__ = ["Diary", "Login", "LoginFlow", "Parent", "RemoteDiary", "Student"]

_CLOSED = "Diary закрыт"


class _Portal:
    """Поток с циклом событий; из любого другого потока в него отправляют корутины."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._lock = threading.Lock()
        self._closed = False
        self._thread = threading.Thread(target=self._serve, name="diarysdk-sync", daemon=True)
        self._thread.start()

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    def _serve(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
        # Незавершённые вызовы других потоков получают CancelledError, а не вечное ожидание.
        tasks = asyncio.all_tasks(self._loop)
        for task in tasks:
            task.cancel()
        self._loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        self._loop.run_until_complete(self._loop.shutdown_asyncgens())
        self._loop.close()

    def run[T](self, coro: Coroutine[Any, Any, T]) -> T:
        if threading.current_thread() is self._thread:
            coro.close()
            raise RuntimeError(
                "Синхронный вызов изнутри самой обёртки (например, из хука) зависнет: "
                "используйте async-класс"
            )
        with self._lock:
            if self._closed:
                coro.close()
                raise RuntimeError(_CLOSED)
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result()
        except BaseException:
            # Прерывание (Ctrl-C) или отмена: задача на портале не должна жить дальше сама.
            future.cancel()
            raise

    def build[T](self, make: Callable[[], T]) -> T:
        """Выполнить `make` в потоке цикла: объекты, привязанные к циклу, рождаются там."""

        async def call() -> T:
            return make()

        return self.run(call())

    def stop(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._loop.call_soon_threadsafe(self._loop.stop)
        if threading.current_thread() is not self._thread:
            self._thread.join()


class _Proxy:
    """Основа обёрток: цель в потоке портала и перевод её результатов."""

    def __init__(self, portal: _Portal, target: Any) -> None:
        self._portal = portal
        self._target = target

    def __repr__(self) -> str:
        return f"sync.{self._target!r}"

    def _adopt(self, value: Any) -> Any:
        if value is self._target:
            return self
        for types, proxy in _ADOPTED:
            if isinstance(value, types):
                return proxy(self._portal, value)
        return value

    def _call(self, name: str, args: tuple, kwargs: dict[str, Any]) -> Any:
        method = getattr(self._target, name)

        async def invoke() -> Any:
            return await method(*args, **kwargs)

        try:
            result = self._portal.run(invoke())
        except (BadCode, BadCaptcha) as error:
            # Поток для повтора — тоже синхронный.
            if error.flow is not None:
                error.flow = self._adopt(error.flow)
            raise
        return self._adopt(result)


def _async_method(name: str, protocol_method: Callable) -> Callable:
    def method(self: _Proxy, *args: Any, **kwargs: Any) -> Any:
        return self._call(name, args, kwargs)

    return _like(method, name, protocol_method)


def _plain_method(name: str, protocol_method: Callable) -> Callable:
    def method(self: _Proxy, *args: Any, **kwargs: Any) -> Any:
        return self._adopt(getattr(self._target, name)(*args, **kwargs))

    return _like(method, name, protocol_method)


def _like(function: Callable, name: str, source: Callable) -> Callable:
    """Имя, описание и сигнатура — как у метода протокола; `async` в сигнатуре нет."""
    function.__name__ = function.__qualname__ = name
    function.__doc__ = source.__doc__
    function.__signature__ = inspect.signature(source)  # type: ignore[attr-defined]
    return function


def _property(name: str, doc: str | None = None) -> property:
    def getter(self: _Proxy) -> Any:
        return self._adopt(getattr(self._target, name))

    getter.__name__ = name
    return property(getter, doc=doc)


def _generate(name: str, protocol: type, base: type = _Proxy, skip: frozenset[str] = frozenset()):
    """Класс-обёртка по протоколу: async-методы синхронные, остальное пересылается."""
    namespace: dict[str, Any] = {"__module__": __name__, "__doc__": protocol.__doc__}
    for member in typing.get_protocol_members(protocol):
        if member in skip or (member.startswith("_") and member not in {"__aenter__", "__aexit__"}):
            continue
        raw = inspect.getattr_static(protocol, member)
        if isinstance(raw, property):
            namespace[member] = _property(member, raw.__doc__)
        elif inspect.iscoroutinefunction(raw):
            namespace[member] = _async_method(member, raw)
        else:
            namespace[member] = _plain_method(member, raw)
    return type(name, (base,), namespace)


_DIARY_ASYNC_ONLY = frozenset({"aclose", "__aenter__", "__aexit__"})

Login = _generate("Login", protocols.LoginLike)
LoginFlow = _generate("LoginFlow", protocols.LoginFlowLike)
Student = _generate("Student", protocols.StudentLike)
Parent = _generate("Parent", protocols.ParentLike)
_DiaryBase = _generate("_DiaryBase", protocols.DiaryLike, skip=_DIARY_ASYNC_ONLY)

_ADOPTED: list[tuple[tuple[type, ...], type[_Proxy]]] = [
    ((_AsyncLogin, _AsyncRemoteLogin), Login),
    ((_AsyncLoginFlow, _AsyncRemoteLoginFlow), LoginFlow),
    ((_AsyncStudent, _AsyncRemoteStudent), Student),
    ((_AsyncParent, _AsyncRemoteParent), Parent),
]


class _Sync(_DiaryBase):
    """Дневник в своём потоке: контекстный менеджер и `close()`."""

    _async_class: type

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        portal = _Portal()
        try:
            target = portal.build(lambda: self._async_class(*args, **kwargs))
        except BaseException:
            portal.stop()
            raise
        super().__init__(portal, target)

    def __enter__(self) -> Self:
        try:
            self._portal.run(self._target.__aenter__())
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Закрыть дневник и остановить поток; повторный вызов не ошибка."""
        try:
            if not self._portal.closed:
                self._portal.run(self._target.aclose())
        finally:
            self._portal.stop()


def _entry(name: str, async_class: type) -> type[_Sync]:
    def init(self: _Sync, *args: Any, **kwargs: Any) -> None:
        _Sync.__init__(self, *args, **kwargs)

    init.__name__ = init.__qualname__ = "__init__"
    init.__signature__ = inspect.signature(async_class.__init__)  # type: ignore[attr-defined]
    namespace = {
        "__module__": __name__,
        "__doc__": async_class.__doc__,
        "_async_class": async_class,
        "__init__": init,
    }
    return type(name, (_Sync,), namespace)


Diary = _entry("Diary", _AsyncDiary)
RemoteDiary = _entry("RemoteDiary", _AsyncRemoteDiary)
