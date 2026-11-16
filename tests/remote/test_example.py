"""examples/bot_flow.py целиком: вход с капчей и кодом, чтение, запись, повторный вход."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport

from diarysdk.models.homework import Homework
from diarysdk.models.school import School
from tests.remote.esia import EsiaDiary, Session
from tests.remote.helpers import remote_diary

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "bot_flow.py"


def load_example():
    spec = importlib.util.spec_from_file_location("bot_flow", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_bot_flow_runs_against_fake_service(app, fake_diary, capsys):
    assert isinstance(fake_diary, EsiaDiary)
    fake_diary.answers["school"] = School(name="Гимназия")
    fake_diary.answers["homework"] = [Homework(id=5, is_done=False)]
    fake_diary.answers["set_homework_done"] = None
    bot = load_example()
    asked = []

    def ask(what):
        asked.append(what)
        return "ответ" if what == "captcha" else "246813"

    async with remote_diary(
        "http://t", "login-key", transport=ASGITransport(app), on_token_expired=bot.on_expired
    ) as api:
        store = bot.TokenStore()
        await bot.handle_user(api, store, "user-1", "login", "password", ask)
        saved = store.get("user-1")
        assert saved is not None
        assert saved.method == "esia"
        assert asked == ["captcha", "code"]

        # Второй заход: токен уже есть, входить заново не нужно.
        await bot.handle_user(api, store, "user-1", "login", "password", ask)
        assert asked == ["captcha", "code"]

        # Токен вот-вот истечёт: бот входит снова, а не ждёт отказа.
        store.put("user-1", saved.__class__(saved.value, datetime.now(UTC) + timedelta(seconds=30)))
        fake_diary.answers["esia_start"] = (Session("captcha"), fake_diary.answers["esia_start"][1])
        await bot.handle_user(api, store, "user-1", "login", "password", ask)
        assert asked == ["captcha", "code"] * 2

    out = capsys.readouterr().out
    assert "Гимназия" in out
    assert "password" not in out
    assert saved.value not in out


async def test_example_main_needs_environment(monkeypatch):
    bot = load_example()
    monkeypatch.delenv("DIARYSDK_URL", raising=False)
    with pytest.raises(SystemExit):
        await bot.main()


@pytest.mark.parametrize(
    ("status", "body", "headers", "expected"),
    [
        (429, {"error": "rate_limited", "message": "x"}, {}, "Слишком часто"),
        (401, {"error": "flow_expired", "message": "x"}, {}, "Вход не удался"),
        (202, {"flow_id": "f", "step": "passkey"}, {}, "Вход не удался"),
    ],
)
async def test_bot_flow_survives_what_a_bot_meets(status, body, headers, expected, capsys):
    import httpx

    bot = load_example()
    transport = httpx.MockTransport(lambda r: httpx.Response(status, json=body, headers=headers))
    async with remote_diary("http://t", "k", transport=transport, max_rate_wait=0) as api:
        await bot.handle_user(api, bot.TokenStore(), "u", "login", "password", lambda what: "x")
    assert expected in capsys.readouterr().out
