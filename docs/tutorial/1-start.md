# 1. Первые шаги

[Документация](../index.md) » [Учебник](index.md) » 1. Первые шаги

## 1.1. Что такое DiarySDK

«Моя школа» — электронный дневник школ Московской области. У него есть сайт и
мобильное приложение, но нет открытого API для программ. DiarySDK даёт такой
API на Python: оценки, расписание, домашние задания, рейтинг, учебный план и
остальное — обычными методами и моделями.

Пакет состоит из трёх частей:

- **ядро** — [`diarysdk.Diary`](../library/diarysdk.md#diarysdk.Diary): само ходит
  в дневник, асинхронное;
- **удалённый клиент** —
  [`diarysdk.remote.RemoteDiary`](../library/remote.md#diarysdk.remote.RemoteDiary):
  тот же интерфейс, но запросы идут в ваш сервис DiarySDK;
- **сервис** — `python -m diarysdk.server`: HTTP API над ядром с ключами,
  лимитами и журналом.

Методы, сигнатуры и исключения у ядра и удалённого клиента одинаковые. Для
кода без `async` есть [`diarysdk.sync`](../library/sync.md).

> [!IMPORTANT]
> Дневник и Госуслуги отвечают только на запросы с российских IP-адресов.
> Ядро и сервис должны работать там, откуда дневник доступен. Если ваш код
> работает за границей, поднимите сервис в России и ходите в него удалённым
> клиентом — [глава 7](7-service.md).

## 1.2. Установка

Нужен Python 3.15 или новее.

```sh
pip install "diarysdk @ git+https://github.com/Kriolt/DiarySDK@v0.2.0"
```

Ядро зависит только от `httpx`, `pydantic` и `tzdata`. Сервису нужны FastAPI и
uvicorn — их ставит extra `server`:

```sh
pip install "diarysdk[server] @ git+https://github.com/Kriolt/DiarySDK@v0.2.0"
```

## 1.3. Первый запрос

Все запросы идут от имени ученика, по его **токену** — JWT дневника. Как
получить токен, рассказано в [главе 3](3-login.md); пока считаем, что он
лежит в переменной окружения `DIARY_TOKEN`.

<!-- test -->
```python
import asyncio
import os

from diarysdk import Diary


async def main() -> None:
    async with Diary() as api:
        student = api.student(os.environ["DIARY_TOKEN"])
        school = await student.school()
        print("Школа:", school.name)


asyncio.run(main())
```

Что здесь происходит:

1. `Diary()` создаёт ядро. Оно держит соединения, поэтому открываем его через
   `async with` — на выходе соединения закроются сами.
2. `api.student(token)` возвращает [`Student`](../library/diarysdk.md#diarysdk.Student).
   В сеть он пока не ходит.
3. `await student.school()` — первый настоящий запрос. Ядро узнаёт у дневника,
   кто владелец токена, и запрашивает его школу. Результат — модель
   [`School`](../library/models.md#diarysdk.models.School).

Дальше — [чтение данных](2-reading.md).
