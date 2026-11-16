"""Цикл бота целиком: вход через Госуслуги, хранение токена, чтение, запись, повторный вход.

Запуск против настоящего сервиса (ключ с разрешением login):

    DIARYSDK_URL=https://diarysdk.example DIARYSDK_KEY=<ключ> \
    ESIA_LOGIN=<логин Госуслуг> python bot_flow.py

Пароль спросит getpass. В тестах этот же файл идёт против фейкового сервиса.
Токен здесь лежит в словаре; у бота это таблица `user_id -> токен, срок`.
"""

import asyncio
import getpass
import os
import sys
from collections.abc import Callable

from diarysdk import (
    BadCaptcha,
    BadCode,
    BadCredentials,
    DiaryLike,
    FlowExpired,
    LoginBlocked,
    NetworkError,
    RateLimited,
    Token,
    TokenExpired,
    UnsupportedStep,
    UpstreamError,
    WriteUncertain,
)
from diarysdk.remote import RemoteDiary


class TokenStore:
    """Хранилище токенов бота. SDK токен не хранит: это забота потребителя."""

    def __init__(self) -> None:
        self._tokens: dict[str, Token] = {}

    def get(self, user_id: str) -> Token | None:
        return self._tokens.get(user_id)

    def put(self, user_id: str, token: Token) -> None:
        self._tokens[user_id] = token

    def drop(self, user_id: str) -> None:
        self._tokens.pop(user_id, None)


def on_expired(token: Token) -> None:
    # Хук зовётся один раз на каждый отказ `token_expired`. Здесь — только сигнал;
    # само «зовите ученика войти» делает вызывающий код, поймав TokenExpired.
    print("Токен истёк:", token)


async def sign_in(api: DiaryLike, login: str, password: str, ask: Callable[[str], str]) -> Token:
    """Вход через Госуслуги; `ask("captcha")` и `ask("code")` спрашивают ученика."""
    result = await api.login.esia(login, password)
    while not isinstance(result, Token):
        flow = result
        try:
            if flow.kind == "captcha":
                # Картинка — flow.captcha.image (bytes): покажите её ученику.
                result = await flow.answer_captcha(ask("captcha"))
            else:
                result = await flow.submit_code(ask("code"))
        except (BadCode, BadCaptcha) as wrong:
            # Ошибка ответа: поток жив, у ошибки готов следующий шаг.
            result = wrong.flow
            if result is None:
                raise
    return result


async def handle_user(
    api: DiaryLike,
    store: TokenStore,
    user_id: str,
    login: str,
    password: str,
    ask: Callable[[str], str],
) -> None:
    token = store.get(user_id)
    if token is None or token.is_expiring():
        # Заходим заранее, не дожидаясь отказа посреди работы.
        try:
            token = await sign_in(api, login, password, ask)
        except (BadCredentials, LoginBlocked) as error:
            print("Войти не вышло:", error.message)
            return
        except RateLimited as error:
            # Старты входа ограничены на весь ключ бота, не на ученика.
            print(f"Слишком часто, повторите через {error.retry_after or 60:.0f} с")
            return
        except (FlowExpired, UnsupportedStep, BadCode, BadCaptcha) as error:
            # Поток истёк (5 минут), шаг клиенту незнаком или ответ неверен и
            # продолжить нельзя (BadCode/BadCaptcha без .flow): начать заново.
            print("Вход не удался, начните заново:", error.message)
            return
        except UpstreamError, NetworkError:
            # Шаг входа не повторяется сам: поток закрыт,
            # начните вход заново позже.
            print("Сервис недоступен, попробуйте позже")
            return
        store.put(user_id, token)

    student = api.student(token)
    try:
        school = await student.school()
        print("Школа:", school.name)
        todo = [item for item in await student.homework() if not item.is_done]
        if todo and todo[0].id is not None:
            try:
                await student.homework_done(todo[0].id)
            except WriteUncertain:
                # Неизвестно, применилась ли отметка: перечитать, а не повторять.
                await student.homework()
    except TokenExpired:
        store.drop(user_id)
        print("Токен истёк: пусть ученик войдёт заново")


async def main() -> None:
    url, key, login = (os.environ.get(n) for n in ("DIARYSDK_URL", "DIARYSDK_KEY", "ESIA_LOGIN"))
    if not (url and key and login):
        sys.exit("Нужны DIARYSDK_URL, DIARYSDK_KEY и ESIA_LOGIN")
    password = getpass.getpass("Пароль Госуслуг: ")
    # Прямой доступ к дневнику — `Diary()` вместо `RemoteDiary(url, key, ...)`: остальное то же.
    async with RemoteDiary(url, key, on_token_expired=on_expired) as api:
        await handle_user(api, TokenStore(), "me", login, password, lambda what: input(f"{what}: "))


if __name__ == "__main__":
    asyncio.run(main())
