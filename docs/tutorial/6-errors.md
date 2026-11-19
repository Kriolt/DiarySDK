# 6. Ошибки

[Документация](../index.md) » [Учебник](index.md) » 6. Ошибки

## 6.1. Иерархия

Все исключения SDK — наследники
[`DiaryError`](../library/errors.md#diarysdk.errors.DiaryError). У каждого
есть `message` (по-русски, без секретов), стабильный машинный код `code`,
`status` и `retry_after`. Ловить удобно по группам:

| Ловите | Значит | Что делать |
| --- | --- | --- |
| `AuthError` | токен или вход не приняты | позвать пользователя входить заново |
| `BadRequest`, `NotFound`, `NotForRole` | запрос неверный или данных нет | исправить запрос |
| `RateLimited` | слишком часто | подождать `retry_after` секунд |
| `UpstreamError` | дневник недоступен или ответил непонятно | повторить позже |
| `WriteUncertain` | запись могла примениться | перечитать состояние |
| `RemoteError` | только у удалённого клиента: сервис недоступен или ключ не подходит | проверить адрес, сеть, ключ |

Полное дерево и все коды — в [справочнике](../library/errors.md).

## 6.2. Типичная обработка

<!-- test -->
```python
import asyncio
import os

from diarysdk import Diary, RateLimited, TokenExpired, UpstreamError


async def main() -> None:
    async with Diary() as api:
        student = api.student(os.environ["DIARY_TOKEN"])
        try:
            print(len(await student.marks()), "оценок")
        except TokenExpired:
            print("ученику нужно войти заново")
        except RateLimited as error:
            print("слишком часто, повторите через", error.retry_after)
        except UpstreamError:
            print("дневник недоступен, попробуйте позже")


asyncio.run(main())
```

> [!TIP]
> Исключения можно смело писать в журнал: пароли, коды, ответы капчи и токены
> в их текст и `repr` не попадают.

Дальше — [свой сервис](7-service.md).
