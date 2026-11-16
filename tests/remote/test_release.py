"""Выпуск: снимок схемы свежий, имя модели ответа входа не прежнее."""

import json
from pathlib import Path

import diarysdk
from diarysdk.server.app import create_app

OPENAPI = Path(__file__).resolve().parents[1] / "openapi.json"


def test_openapi_snapshot_is_current(settings):
    snapshot = json.loads(OPENAPI.read_text(encoding="utf-8"))
    live = create_app(settings).openapi()
    # Через json, чтобы сравнивать то же, что лежит в файле (кортежи, ключи).
    assert json.loads(json.dumps(live)) == snapshot, (
        "tests/openapi.json устарел: python scripts/openapi_snapshot.py"
    )


def test_token_model_is_token_response_without_old_alias():
    from diarysdk.models import auth as models

    assert not hasattr(models, "Token")
    # Клиентский класс Token — не модель ответа.
    assert diarysdk.Token is not models.TokenResponse


def test_openapi_names_token_response(settings):
    schemas = create_app(settings).openapi()["components"]["schemas"]
    assert "TokenResponse" in schemas
    assert "Token" not in schemas


def test_models_package_reexports_every_public_model():
    import importlib
    import pkgutil

    import diarysdk.models as models

    assert models.__all__ == sorted(models.__all__)
    for info in pkgutil.iter_modules(models.__path__):
        module = importlib.import_module(f"diarysdk.models.{info.name}")
        for name, obj in vars(module).items():
            if (
                isinstance(obj, type)
                and obj.__module__ == module.__name__
                and not name.startswith("_")
                and name != "Schema"
            ):
                assert getattr(models, name) is obj, f"{info.name}.{name} не в diarysdk.models"
