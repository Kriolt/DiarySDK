# 3. Вход и токены

[Документация](../index.md) » [Учебник](index.md) » 3. Вход и токены

Токен получают тремя способами, и любой из них даёт объект
[`Token`](../library/token.md#diarysdk.Token).

## 3.1. Готовый токен

Если JWT дневника уже есть, передайте строку прямо в `api.student(token)` или
оберните её: `Token("eyJ...")`. Срок SDK читает из самого токена.

## 3.2. Вход по логину и паролю

Логин и пароль портала «Моя школа»:

<!-- test -->
```python
import asyncio

from diarysdk import Diary


async def main() -> None:
    async with Diary() as api:
        token = await api.login.password("login", "password")
        print(token.method, token.expires_at is not None)


asyncio.run(main())
```

Неверная пара — [`BadCredentials`](../library/errors.md#diarysdk.errors.BadCredentials),
временная блокировка — [`LoginBlocked`](../library/errors.md#diarysdk.errors.LoginBlocked).

## 3.3. Вход через Госуслуги

Госуслуги могут попросить капчу и код из SMS, приложения или MAX, поэтому
[`login.esia()`](../library/diarysdk.md#diarysdk.Login.esia) возвращает либо
`Token`, либо [`LoginFlow`](../library/diarysdk.md#diarysdk.LoginFlow) — вход,
который ждёт ответа. Отвечайте, пока не получите токен:

<!-- test -->
```python
import asyncio

from diarysdk import Diary, Token


async def main() -> None:
    async with Diary() as api:
        result = await api.login.esia("login", "password")
        while not isinstance(result, Token):
            if result.kind == "captcha":
                # result.captcha.image — картинка (bytes): покажите её пользователю.
                result = await result.answer_captcha(input("Капча: "))
            else:
                # result.mfa.kind — куда ушёл код: sms, totp или max.
                result = await result.submit_code(input("Код: "))
        print("Вошли:", result.method)


asyncio.run(main())
```

Поток живёт 5 минут с последнего шага; потом —
[`FlowExpired`](../library/errors.md#diarysdk.errors.FlowExpired).

Неверный ответ не убивает вход. У исключений
[`BadCode`](../library/errors.md#diarysdk.errors.BadCode) и
[`BadCaptcha`](../library/errors.md#diarysdk.errors.BadCaptcha) есть атрибут
`flow` — тот же поток, готовый к следующей попытке (или `None`, если
продолжить нельзя):

```python
try:
    result = await flow.submit_code(code)
except BadCode as error:
    if error.flow is None:
        raise
    flow = error.flow  # попросить код ещё раз; error.flow.mfa.attempts_left
```

Полный разбор всех случаев для бота — в
[`examples/bot_flow.py`](../../examples/bot_flow.py).

> [!NOTE]
> Пароли, коды и ответы капчи SDK нигде не сохраняет; они не попадают в
> `repr`, исключения и журналы.

## 3.4. Хранение токена

SDK **не хранит токены** — это забота вашего приложения. Токен — секрет,
поэтому `repr()` и `str()` показывают только метод, срок и короткую метку
хеша, а само значение отдаётся явно — через `token.value`. Сохраните значение,
срок и метод, а потом восстановите `Token`:

<!-- test -->
```python
from datetime import UTC, datetime, timedelta

from diarysdk import Token

token = Token("значение-токена", datetime.now(UTC) + timedelta(hours=8), method="esia")

row = {"value": token.value, "expires_at": token.expires_at, "method": token.method}
restored = Token(row["value"], row["expires_at"], row["method"])

print(restored)  # Token(method=esia, expires_at=..., sha256=...)
if restored.is_expiring():  # осталось меньше 5 минут или уже истёк
    print("пора входить заново")
```

Если срок неизвестен (`expires_at` равен `None`), `is_expiring()` возвращает
`False`, но перед запросом ядро такой токен отвергнет как
[`TokenInvalid`](../library/errors.md#diarysdk.errors.TokenInvalid). Токен с
вышедшим сроком отвергается как
[`TokenExpired`](../library/errors.md#diarysdk.errors.TokenExpired) — тоже без
обращения к дневнику.

Дальше — [родитель](4-parent.md).
