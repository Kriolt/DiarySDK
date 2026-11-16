"""Проверка чистоты репозитория перед публикацией.

    python scripts/check_clean.py [--extra FILE] [--history]

Общие правила (встроены): абсолютные домашние пути, файлы probe*.json,
JWT, почтовые адреса, российские телефоны. Явно фальшивые значения
разрешены:

* JWT — только с подписью `c2lnbmF0dXJl` (как у подставных токенов тестов);
* почта — `*@users.noreply.github.com`, `noreply@anthropic.com`, домены
  `example.com|org|net` и их поддомены, зоны `.example`, `.test`,
  `.invalid`, `.localhost`; `user@host` сразу после `://` — не почта;
  `имя@v0.1.0` (последняя метка из одних цифр — тег версии, не домен) — не почта;
* телефон — если код (первая группа из трёх цифр) равен `000` или
  последние семь цифр нули. Число из одиннадцати цифр без разделителей,
  начинающееся с 8 и не с 89, телефоном не считается (это не мобильный).

`--extra FILE` — локальный список регулярных выражений без учёта
регистра (по одному в строке, `#` — комментарий, встроенные флаги вида
`(?-i:...)` допустимы). Совпавший текст не печатается: выводится номер
строки правила в файле списка.

Проверяются содержимое и имена всех файлов из `git ls-files --cached
--others --exclude-standard` (отслеживаемые и неотслеживаемые, но не
игнорируемые); файлы с нулевым байтом считаются двоичными и по
содержимому не проверяются, имя проверяется всегда. С
`--history` ещё и авторы и сообщения всех коммитов. Вывод —
`путь:строка: правило`, код выхода 1 при любой находке.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

FAKE_JWT_SIGNATURE = "c2lnbmF0dXJl"
_FAKE_ZONES = {"test", "example", "invalid", "localhost"}
_FAKE_DOMAINS = {"example.com", "example.org", "example.net"}

_HOME = re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+/|C:\\Users\\", re.IGNORECASE)
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.([A-Za-z0-9_-]*)")
_EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
_PHONE = re.compile(
    r"(?<![\w.])(?:\+7|8)[\s(-]*(\d{3})[\s)-]*(\d{3})[\s-]*(\d{2})[\s-]*(\d{2})(?![\w])"
)
_PROBE_NAME = re.compile(r"^probe.*\.json$", re.IGNORECASE)


def _email_ok(line: str, match: re.Match[str]) -> bool:
    if line[max(0, match.start() - 3) : match.start()] == "://":
        return True  # user@host в URL — не почта
    domain = match.group(1).lower()
    if domain.rsplit(".", 1)[-1].isdigit():
        return True  # `Репозиторий@v0.1.0`: тег версии в адресе установки
    if match.group(0).lower() == "noreply@anthropic.com":
        return True
    if domain == "users.noreply.github.com" or domain.endswith(".users.noreply.github.com"):
        return True
    if domain.rsplit(".", 1)[-1] in _FAKE_ZONES:
        return True
    return any(domain == d or domain.endswith(f".{d}") for d in _FAKE_DOMAINS)


def _phone_ok(match: re.Match[str]) -> bool:
    code, *rest = match.groups()
    digits = "".join(rest)
    if code == "000" or set(digits) == {"0"}:
        return True
    text = match.group(0)
    return text.isdigit() and text[0] == "8" and text[1] != "9"


def generic_line_rules(line: str) -> list[str]:
    """Имена общих правил, сработавших на строке."""
    hits: list[str] = []
    if _HOME.search(line):
        hits.append("домашний путь")
    if any(m.group(1) != FAKE_JWT_SIGNATURE for m in _JWT.finditer(line)):
        hits.append("JWT")
    if any(not _email_ok(line, m) for m in _EMAIL.finditer(line)):
        hits.append("почтовый адрес")
    if any(not _phone_ok(m) for m in _PHONE.finditer(line)):
        hits.append("телефон")
    return hits


def generic_name_rules(path: str) -> list[str]:
    """Правила, сработавшие на имени файла."""
    hits = ["файл probe*.json"] if _PROBE_NAME.match(Path(path).name) else []
    hits += generic_line_rules(path)
    return hits


def load_extra(path: Path) -> list[tuple[int, re.Pattern[str]]]:
    """Регулярные выражения со списка: (номер строки, шаблон)."""
    rules = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = raw.strip()
        if text and not text.startswith("#"):
            rules.append((number, re.compile(text, re.IGNORECASE)))
    return rules


def scan_text(label: str, text: str, extra: list[tuple[int, re.Pattern[str]]]) -> list[str]:
    """Находки в тексте: строки `метка:строка: правило`."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        found += [f"{label}:{number}: {rule}" for rule in generic_line_rules(line)]
        found += [
            f"{label}:{number}: правило {rule_line} из дополнительного списка"
            for rule_line, pattern in extra
            if pattern.search(line)
        ]
    return found


def scan_name(path: str, extra: list[tuple[int, re.Pattern[str]]]) -> list[str]:
    found = [f"{path}:0: имя файла: {rule}" for rule in generic_name_rules(path)]
    found += [
        f"{path}:0: имя файла: правило {rule_line} из дополнительного списка"
        for rule_line, pattern in extra
        if pattern.search(path)
    ]
    return found


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout  # noqa: S603, S607 - git из PATH, аргументы фиксированы


def scan_tree(root: Path, extra: list[tuple[int, re.Pattern[str]]]) -> list[str]:
    found = []
    listing = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    for name in sorted(set(listing.decode("utf-8").split("\0"))):
        if not name:
            continue
        found += scan_name(name, extra)
        path = root / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" not in data:
            found += scan_text(name, data.decode("utf-8", errors="replace"), extra)
    return found


def scan_history(root: Path, extra: list[tuple[int, re.Pattern[str]]]) -> list[str]:
    fmt = "%x01%h%n%an%n%ae%n%cn%n%ce%n%B"
    log = _git(root, "log", "--all", f"--format={fmt}").decode("utf-8", errors="replace")
    found = []
    for entry in log.split("\x01")[1:]:
        short, _, body = entry.partition("\n")
        found += scan_text(f"коммит {short}", body, extra)
    return found


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка чистоты репозитория.")
    parser.add_argument("--extra", type=Path, help="локальный список регулярных выражений")
    parser.add_argument("--history", action="store_true", help="проверить и историю git")
    args = parser.parse_args(argv)
    root = root or Path(__file__).resolve().parents[1]
    extra = load_extra(args.extra) if args.extra else []
    found = scan_tree(root, extra)
    if args.history:
        found += scan_history(root, extra)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
