"""Проверяет состав собранных архивов: `python scripts/check_dist.py <каталог dist>`.

В wheel — пакет с `py.typed` и `sync.pyi`, без тестов, документов и скриптов.
В sdist — ни внутренних заметок, ни окружения. Код выхода 1 при любой находке.
"""

import sys
import tarfile
import zipfile
from pathlib import Path

WHEEL_REQUIRED = ("diarysdk/py.typed", "diarysdk/sync.pyi", "diarysdk/__init__.py")
WHEEL_FORBIDDEN = ("tests/", "docs/", "scripts/", "examples/", ".superpowers/", ".venv/")
SDIST_FORBIDDEN = ("docs/internal", ".superpowers", ".venv", ".git/", "__pycache__", ".env")


def wheel_problems(path: Path) -> list[str]:
    names = zipfile.ZipFile(path).namelist()
    problems = [f"{path.name}: нет {need}" for need in WHEEL_REQUIRED if need not in names]
    problems += [
        f"{path.name}: лишнее {name}"
        for name in names
        for bad in WHEEL_FORBIDDEN
        if name.startswith(bad)
    ]
    return problems


def sdist_problems(path: Path) -> list[str]:
    with tarfile.open(path) as archive:
        # Первый компонент — каталог `diarysdk-<версия>`, его отбрасываем.
        names = [name.split("/", 1)[1] for name in archive.getnames() if "/" in name]
    return [
        f"{path.name}: лишнее {name}"
        for name in names
        for bad in SDIST_FORBIDDEN
        if name == bad or name.startswith(bad) or f"/{bad}" in f"/{name}"
    ]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    dist = Path(argv[1])
    wheels, sdists = sorted(dist.glob("*.whl")), sorted(dist.glob("*.tar.gz"))
    problems = [] if wheels and sdists else [f"{dist}: нужны и wheel, и sdist"]
    for wheel in wheels:
        problems += wheel_problems(wheel)
    for sdist in sdists:
        problems += sdist_problems(sdist)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
