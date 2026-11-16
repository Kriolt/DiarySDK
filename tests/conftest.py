from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from diarysdk import _clock as clock
from diarysdk.server.app import create_app
from diarysdk.server.config import Settings
from diarysdk.server.keys import hash_key
from tests.fakes import FakeDiary, core_diary
from tests.tokens import valid_token

API_KEY = "test-key"
KEY_HEADERS = {"X-Api-Key": API_KEY}
TOKEN = valid_token()
AUTH_HEADERS = {**KEY_HEADERS, "Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def keys_file(tmp_path):
    path = tmp_path / "api-keys"
    path.write_text(f"tests {hash_key(API_KEY)}\n")
    return path


@pytest.fixture
def settings(keys_file):
    return Settings(keys_file=keys_file, version="abc1234")


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app), base_url="http://diarysdk.test") as c:
        yield c


@pytest.fixture
def fake_diary():
    return FakeDiary()


@pytest.fixture
def today(monkeypatch):
    """«Сегодня» для ядра — суббота 24 октября 2026."""
    day = date(2026, 10, 24)
    monkeypatch.setattr(clock, "today_msk", lambda: day)
    return day


@pytest.fixture
async def api(settings, fake_diary, today):
    """Клиент настоящего приложения с подставным Diary и ключом с токеном."""
    app = create_app(settings, diary=core_diary(fake_diary))
    transport = ASGITransport(app)
    async with AsyncClient(transport=transport, base_url="http://t", headers=AUTH_HEADERS) as c:
        yield c


def _schema_classes():
    import importlib
    import pkgutil

    import diarysdk.models as models
    from diarysdk.models.common import Schema

    for info in pkgutil.iter_modules(models.__path__):
        importlib.import_module(f"{models.__name__}.{info.name}")
    seen, todo = [], [Schema]
    while todo:
        cls = todo.pop()
        if cls not in seen:
            seen.append(cls)
            todo.extend(cls.__subclasses__())
    return seen


_extra_mode = "ignore"


def set_schema_extra(mode: str) -> None:
    """Переключает extra у всех моделей ответов (и перестраивает их схемы).

    Клиент по умолчанию пропускает лишние поля (ignore). Тесты сервиса идут в
    режиме forbid: опечатка в имени поля при сборке ответа тогда падает, а не
    теряется молча.
    """
    global _extra_mode
    if mode == _extra_mode:
        return
    classes = _schema_classes()
    for cls in classes:
        cls.model_config["extra"] = mode
    # Вложенные схемы вшиваются в родителей при сборке: перестраиваем несколько
    # проходов, чтобы глубина вложенности не мешала.
    for _ in range(6):
        for cls in classes:
            cls.model_rebuild(force=True)
    from diarysdk.remote._core import _adapter

    _adapter.cache_clear()
    _extra_mode = mode


@pytest.fixture(autouse=True)
def _schema_extra_mode(request):
    in_client = "remote" in request.path.parts[-2:-1]
    set_schema_extra("ignore" if in_client else "forbid")
