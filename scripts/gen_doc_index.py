"""Собирает алфавитный указатель `docs/genindex.md`: `python scripts/gen_doc_index.py`.

Источник — записи справочника `docs/library/*.md`: якорь `<a id="имя"></a>`, за
ним заголовок `### *вид* `сигнатура``. Тест сверяет указатель с этим выводом.
"""

import re
from collections import defaultdict
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
TARGET = DOCS / "genindex.md"
ENTRY = re.compile(r'^<a id="([^"]+)"></a>\n\n#{3,4} \*([^*]+)\* `([^`]+)`', re.MULTILINE)
CALLABLE = {"метод", "async-метод", "функция"}
HEADER = """\
# Алфавитный указатель

[Документация](index.md) » Алфавитный указатель

<!-- Собран scripts/gen_doc_index.py из docs/library/*.md; руками не правится. -->
"""


def entries() -> list[tuple[str, str, str, str]]:
    """(имя, вид, владелец, ссылка) для каждой записи справочника."""
    result = []
    for path in sorted((DOCS / "library").glob("*.md")):
        for anchor, kind, signature in ENTRY.findall(path.read_text()):
            owner, _, name = anchor.rpartition(".")
            # Запись уровня модуля пишет полное имя: `diarysdk.Diary(...)`.
            if not signature.startswith(anchor):
                kind = f"{kind} {owner}"
            else:
                kind = f"{kind} в {owner}"
            if kind.split()[0] in CALLABLE:
                name += "()"
            result.append((name, kind, owner, f"library/{path.name}#{anchor}"))
    return result


def render() -> str:
    groups: dict[str, list[str]] = defaultdict(list)
    for name, kind, _owner, link in sorted(
        entries(), key=lambda item: (item[0].lstrip("_").lower(), item[1])
    ):
        letter = name.lstrip("_")[0].upper()
        groups[letter].append(f"- [`{name}`]({link}) ({kind})")
    letters = sorted(groups)
    lines = [HEADER, " · ".join(f"[{letter}](#{letter.lower()})" for letter in letters), ""]
    for letter in letters:
        lines += [f"## {letter}", "", *groups[letter], ""]
    return "\n".join(lines)


if __name__ == "__main__":
    TARGET.write_text(render())
