# 7. Свой сервис

[Документация](../index.md) » [Учебник](index.md) » 7. Свой сервис

## 7.1. Зачем нужен сервис

Сервис DiarySDK нужен, когда:

- ваш код работает не в России, а дневник отвечает только российским
  адресам;
- к дневнику ходят несколько программ, и вы хотите одно место с ключами,
  лимитами и журналом;
- клиент написан не на Python — сервису достаточно HTTP
  ([HTTP API](../http.md)).

## 7.2. Запуск

Выпустите ключ потребителя. Сам ключ напечатается один раз в stderr, а в файл
ключей уйдёт строка с его хешем:

```sh
python -m diarysdk.server.keys new bot --scope login >> api-keys
DIARYSDK_KEYS_FILE=./api-keys python -m diarysdk.server
```

Сервис слушает `127.0.0.1:8000`. Разрешения ключей, лимиты, переменные
окружения и Docker — в [справочнике сервиса](../library/server.md).

## 7.3. Удалённый клиент

[`RemoteDiary`](../library/remote.md#diarysdk.remote.RemoteDiary) принимает адрес
сервиса и ключ, а дальше всё как у ядра:

<!-- test -->
```python
import asyncio
import os

from diarysdk.remote import RemoteDiary


async def main() -> None:
    async with RemoteDiary("https://diarysdk.example", "my-api-key") as api:
        student = api.student(os.environ["DIARY_TOKEN"])
        print((await student.school()).name)


asyncio.run(main())
```

Отличий от ядра немного: сетевые сбои до сервиса —
[`NetworkError`](../library/errors.md#diarysdk.errors.NetworkError), неверный
ключ — [`BadApiKey`](../library/errors.md#diarysdk.errors.BadApiKey), нехватка
разрешения — [`ForbiddenScope`](../library/errors.md#diarysdk.errors.ForbiddenScope).

## 7.4. Код для обоих клиентов

Ядро и удалённый клиент отвечают одному протоколу
[`DiaryLike`](../library/diarysdk.md#diarysdk.DiaryLike). Пишите функции против
протокола — и выбирайте клиента в одном месте программы:

<!-- test -->
```python
import asyncio
import os

from diarysdk import Diary, DiaryLike
from diarysdk.remote import RemoteDiary


async def school_name(api: DiaryLike, token: str) -> str | None:
    return (await api.student(token).school()).name


async def main() -> None:
    token = os.environ["DIARY_TOKEN"]
    async with Diary() as direct, RemoteDiary("https://diarysdk.example", "my-api-key") as remote:
        print(await school_name(direct, token), await school_name(remote, token))


asyncio.run(main())
```

## 7.5. Синхронный код

В [`diarysdk.sync`](../library/sync.md) те же `Diary` и `RemoteDiary`, но без
`async` и `await`:

<!-- test -->
```python
import os

from diarysdk.sync import RemoteDiary

with RemoteDiary("https://diarysdk.example", "my-api-key") as api:
    student = api.student(os.environ["DIARY_TOKEN"])
    print(student.school().name)
    print(len(student.marks()), "оценок")
```

Каждый синхронный экземпляр держит свой поток с циклом событий, а вызов
блокирует вызывающий поток. В async-коде пользуйтесь async-классами, а
синхронные экземпляры закрывайте через `with` или `close()`.

На этом учебник закончен. Дальше — [справочник](../library/index.md), а
если что-то непонятно в терминах — [глоссарий](../glossary.md).
