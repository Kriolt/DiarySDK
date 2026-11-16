"""Границы импортов между слоями пакета diarysdk.

Ядро не зависит ни от веб-фреймворков, ни от diarysdk.server; весь сервер знает
из дневника только публичный API и _port/_metrics/_version; относительных
импортов в пакете нет; сторонней библиотеки дневника в коде нет совсем.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "diarysdk"
# Веб-фреймворки живут только в diarysdk.server: ядро ставится без них.
WEB = ("fastapi", "starlette", "uvicorn")
# Внутренности, которых удалённый клиент знать не должен.
REMOTE_FORBIDDEN = ("diarysdk.server", "diarysdk._login", "diarysdk._api", "diarysdk._wire")
# Внутренности дневника, которых sync знать не должен.
DIARY_INTERNALS = (
    "diarysdk._gateway",
    "diarysdk._transport",
    "diarysdk._api",
    "diarysdk._wire",
    "diarysdk._login",
    "diarysdk._hosts",
    "diarysdk._jwt",
    "diarysdk._context",
    "diarysdk._periods",
    "diarysdk._clock",
)
# Приватные модули, которые серверу разрешены: порт (контракт Diary и Ctx),
# счётчик запросов и версия. Всё остальное приватное — только через публичный API.
SERVER_ALLOWED_PRIVATE = (
    "diarysdk._port",
    "diarysdk._metrics",
    "diarysdk._version",
    "diarysdk.__version__",
)
# Сторонняя библиотека дневника: запросы и модели ответов свои.
# Имя собрано по частям: в репозитории его нет и в виде строки.
THIRD_PARTY_CLIENT = "octo" + "diary"
FORBIDDEN_EVERYWHERE = (THIRD_PARTY_CLIENT, "aiohttp", "requests", "fake_useragent")
LOGIN_FILES = ("_login/password.py", "_login/esia.py", "_login/captcha.py")


def _imported_modules(tree: ast.AST) -> set[str]:
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _relative_imports(tree: ast.AST) -> list[str]:
    return [
        "." * node.level + (node.module or "")
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level > 0
    ]


def _is_private(module: str) -> bool:
    parts = module.split(".")
    return parts[0] == "diarysdk" and len(parts) > 1 and parts[1].startswith("_")


def _under(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _any_under(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(_under(module, prefix) for prefix in prefixes)


def violations(root: Path) -> list[str]:
    found = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(), filename=rel)
        modules = _imported_modules(tree)
        for name in _relative_imports(tree):
            found.append(f"{rel}: относительный импорт {name}, нужен абсолютный")
        in_server = rel.startswith("server/")
        layer = rel.split("/")[1] if in_server and rel.count("/") > 1 else None

        if not in_server:
            for m in sorted(m for m in modules if _any_under(m, WEB)):
                found.append(f"{rel}: ядро не импортирует {m}")
            for m in sorted(m for m in modules if _under(m, "diarysdk.server")):
                found.append(f"{rel}: ядро не импортирует сервер, а тут {m}")

        if rel.startswith("remote/"):
            for m in sorted(m for m in modules if _any_under(m, REMOTE_FORBIDDEN)):
                found.append(f"{rel}: удалённый клиент не импортирует {m}")

        if rel == "sync.py":
            # Синхронные обёртки знают только async-клиенты (client, remote) и протоколы.
            banned = ("diarysdk.server", *REMOTE_FORBIDDEN, *DIARY_INTERNALS)
            for m in sorted(m for m in modules if _any_under(m, banned)):
                found.append(f"{rel}: sync знает только client и remote, а импортирует {m}")

        if in_server:
            scope = layer or "server"
            for m in sorted(modules):
                if _is_private(m) and not _any_under(m, SERVER_ALLOWED_PRIVATE):
                    found.append(f"{rel}: {scope} не импортирует приватный {m}")

        if rel in LOGIN_FILES:
            # Вход идёт через транспорт: ни шлюз, ни чтение из _api ему не нужны.
            banned = ("diarysdk._api", "diarysdk._gateway")
            for m in sorted(m for m in modules if _any_under(m, banned)):
                found.append(f"{rel}: вход идёт через транспорт, а не через {m}")

        # Одна HTTP-библиотека на пакет (httpx); сторонний клиент дневника не нужен.
        for m in sorted(m for m in modules if _any_under(m, FORBIDDEN_EVERYWHERE)):
            found.append(f"{rel}: {m.split('.')[0]} не импортируется, а тут {m}")
    return found


def test_package_respects_boundaries():
    assert list(PACKAGE.rglob("*.py")), "пакет не найден: тест проверял бы пустоту"
    assert violations(PACKAGE) == []


def test_checker_catches_each_rule(tmp_path):
    files = {
        "server/routes/me.py": "from diarysdk._gateway import DiaryGateway\nimport aiohttp\n",
        "server/services/student.py": "from diarysdk import _mapping\nfrom diarysdk import _port\n",
        "server/services/login.py": "from diarysdk import _jwt as jwt\n",
        "server/edge/errors.py": "from diarysdk import _transport\n",
        "_mapping/me.py": (
            f"from {THIRD_PARTY_CLIENT}.types.web import WebFamilyProfile\n"
            f"import {THIRD_PARTY_CLIENT}.apis\n"
        ),
        "_gateway.py": f"import {THIRD_PARTY_CLIENT}\nfrom diarysdk.server import logs\n",
        "server/app.py": "from diarysdk._hosts import Hosts\nfrom diarysdk import __version__\n",
        "server/keys.py": "from . import logs\nfrom diarysdk._metrics import count_diary_call\n",
        "server/config.py": "from diarysdk import Hosts\nfrom diarysdk._port import FLOW_TTL\n",
        "_api/mobile.py": "import requests\nfrom aiohttp import ClientSession\n",
        "_transport.py": "import aiohttp\nimport httpx\n",
        "_login/password.py": "from diarysdk._api.web import WebAPI\n",
        "_login/esia.py": "from diarysdk import _gateway\n",
        "remote/client.py": "from diarysdk._login import password\nimport fastapi\n",
        "models/me.py": "from starlette.requests import Request\n",
        "sync.py": (
            "from diarysdk._gateway import DiaryGateway\nfrom diarysdk import client\n"
            "from diarysdk import _jwt\n"
        ),
    }
    for rel, source in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(source)

    found = violations(tmp_path)
    T = THIRD_PARTY_CLIENT

    assert found == [
        "_api/mobile.py: aiohttp не импортируется, а тут aiohttp",
        "_api/mobile.py: aiohttp не импортируется, а тут aiohttp.ClientSession",
        "_api/mobile.py: requests не импортируется, а тут requests",
        "_gateway.py: ядро не импортирует сервер, а тут diarysdk.server",
        "_gateway.py: ядро не импортирует сервер, а тут diarysdk.server.logs",
        f"_gateway.py: {T} не импортируется, а тут {T}",
        "_login/esia.py: вход идёт через транспорт, а не через diarysdk._gateway",
        "_login/password.py: вход идёт через транспорт, а не через diarysdk._api.web",
        "_login/password.py: вход идёт через транспорт, а не через diarysdk._api.web.WebAPI",
        f"_mapping/me.py: {T} не импортируется, а тут {T}.apis",
        f"_mapping/me.py: {T} не импортируется, а тут {T}.types.web",
        f"_mapping/me.py: {T} не импортируется, а тут {T}.types.web.WebFamilyProfile",
        "_transport.py: aiohttp не импортируется, а тут aiohttp",
        "models/me.py: ядро не импортирует starlette.requests",
        "models/me.py: ядро не импортирует starlette.requests.Request",
        "remote/client.py: ядро не импортирует fastapi",
        "remote/client.py: удалённый клиент не импортирует diarysdk._login",
        "remote/client.py: удалённый клиент не импортирует diarysdk._login.password",
        "server/app.py: server не импортирует приватный diarysdk._hosts",
        "server/app.py: server не импортирует приватный diarysdk._hosts.Hosts",
        "server/edge/errors.py: edge не импортирует приватный diarysdk._transport",
        "server/keys.py: относительный импорт ., нужен абсолютный",
        "server/routes/me.py: routes не импортирует приватный diarysdk._gateway",
        "server/routes/me.py: routes не импортирует приватный diarysdk._gateway.DiaryGateway",
        "server/routes/me.py: aiohttp не импортируется, а тут aiohttp",
        "server/services/login.py: services не импортирует приватный diarysdk._jwt",
        "server/services/student.py: services не импортирует приватный diarysdk._mapping",
        "sync.py: sync знает только client и remote, а импортирует diarysdk._gateway",
        "sync.py: sync знает только client и remote, а импортирует diarysdk._gateway.DiaryGateway",
        "sync.py: sync знает только client и remote, а импортирует diarysdk._jwt",
    ]
