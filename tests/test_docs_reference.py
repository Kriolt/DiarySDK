"""Справочник docs/: каждое публичное имя описано, поля моделей совпадают с
таблицами, указатель свежий, ссылки ведут в существующие места."""

import importlib.util
import re
from pathlib import Path

import pytest

import diarysdk
import diarysdk.models
import diarysdk.remote
import diarysdk.sync

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
LIBRARY = DOCS / "library"
ANCHOR = re.compile(r'<a id="([^"]+)"></a>')
LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6} (.+)$", re.MULTILINE)
PAGES = sorted([ROOT / "README.md", *(p for p in DOCS.rglob("*.md") if "internal" not in p.parts)])


def _anchors(path: Path) -> set[str]:
    text = path.read_text()
    slugs = {_slug(title) for title in HEADING.findall(_without_code(text))}
    return set(ANCHOR.findall(text)) | slugs


def _without_code(text: str) -> str:
    return re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)


def _slug(title: str) -> str:
    # Как GitHub: нижний регистр, без знаков препинания, пробелы — дефисы.
    title = re.sub(r"[`*]", "", title).strip().lower()
    return re.sub(r"[^\w\- ]", "", title).replace(" ", "-")


LIBRARY_ANCHORS = set().union(*(set(ANCHOR.findall(p.read_text())) for p in LIBRARY.glob("*.md")))


@pytest.mark.parametrize(
    ("module", "prefixes"),
    [
        (diarysdk, ("diarysdk.", "diarysdk.errors.", "diarysdk.models.")),
        (diarysdk.models, ("diarysdk.models.",)),
        (diarysdk.remote, ("diarysdk.remote.",)),
        (diarysdk.sync, ("diarysdk.sync.",)),
    ],
    ids=lambda value: getattr(value, "__name__", ""),
)
def test_every_public_name_has_an_entry(module, prefixes):
    missing = [
        name
        for name in module.__all__
        if not any(prefix + name in LIBRARY_ANCHORS for prefix in prefixes)
    ]
    assert missing == []


def _model_sections() -> dict[str, str]:
    text = (LIBRARY / "models.md").read_text()
    parts = ANCHOR.split(text)
    # split даёт [до, якорь, текст, якорь, текст, ...]
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def _table_fields(section: str) -> set[str]:
    fields = set()
    for line in section.splitlines():
        if line.startswith("| `"):
            first = line.split("|")[1]
            fields.update(re.findall(r"`(\w+)`", first))
    return fields


@pytest.mark.parametrize("name", diarysdk.models.__all__)
def test_model_table_matches_fields(name):
    model = getattr(diarysdk.models, name)
    section = _model_sections()[f"diarysdk.models.{name}"]
    if hasattr(model, "model_fields"):
        expected = set(model.model_fields)
    else:
        expected = set(model.__dataclass_fields__)
    assert _table_fields(section) == expected


def test_genindex_is_fresh():
    spec = importlib.util.spec_from_file_location(
        "gen_doc_index", ROOT / "scripts" / "gen_doc_index.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (DOCS / "genindex.md").read_text() == module.render(), (
        "указатель устарел: python scripts/gen_doc_index.py"
    )


def _local_links():
    for page in PAGES:
        for target in LINK.findall(_without_code(page.read_text())):
            if not target.startswith(("http://", "https://", "mailto:")):
                yield page, target


@pytest.mark.parametrize(
    ("page", "target"),
    list(_local_links()),
    ids=lambda value: value.relative_to(ROOT).as_posix() if isinstance(value, Path) else value,
)
def test_link_resolves(page, target):
    path, _, anchor = target.partition("#")
    destination = (page.parent / path).resolve() if path else page
    assert destination.exists(), f"{page.name}: нет файла {path}"
    if anchor:
        assert destination.is_file(), f"{page.name}: якорь у каталога {path}"
        assert anchor in _anchors(destination), f"{page.name}: нет якоря #{anchor} в {path}"
