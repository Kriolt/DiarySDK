# `diarysdk.remote` — клиент сервиса DiarySDK

[Документация](../index.md) » [Справочник библиотеки](index.md) » `diarysdk.remote`

**Исходный код:** [`diarysdk/remote/`](../../diarysdk/remote/)

---

Удалённый клиент ходит не в дневник, а в [сервис DiarySDK](server.md). Его
интерфейс тот же, что у [ядра](diarysdk.md): одинаковые методы, сигнатуры,
модели и исключения. Код, написанный под [`DiaryLike`](diarysdk.md#diarysdk.DiaryLike),
работает с обоими.

Российский адрес клиенту не нужен: он знает только адрес сервиса.

```python
import asyncio

from diarysdk.remote import RemoteDiary


async def main() -> None:
    async with RemoteDiary("https://diarysdk.example", "my-api-key") as api:
        student = api.student("eyJ...")
        print((await student.school()).name)


asyncio.run(main())
```

<a id="diarysdk.remote.RemoteDiary"></a>

### *класс* `diarysdk.remote.RemoteDiary(base_url, api_key, *, timeout=30.0, max_rate_wait=2.0, on_token_expired=None, http=None)`

Дневник через сервис. Реализует [`DiaryLike`](diarysdk.md#diarysdk.DiaryLike):
`login`, `student(token)`, `parent(token)`, `aclose()`, `async with`.

Параметры:

- **base_url** (`str`) — адрес сервиса.
- **api_key** (`str`) — ключ потребителя; уходит в заголовке `X-Api-Key`.
- **timeout** (`float`) — секунд на один запрос к сервису.
- **max_rate_wait** (`float`) — если сервис ответил `429` с `Retry-After` не
  больше этого числа секунд, клиент один раз подождёт и повторит; иначе
  [`RateLimited`](errors.md#diarysdk.errors.RateLimited).
- **on_token_expired** (функция или async-функция от
  [`Token`](token.md#diarysdk.Token) | `None`) — хук: вызывается один раз на
  каждый отказ `token_expired`, до того как исключение дойдёт до вас. Удобно,
  чтобы пометить токен в хранилище. Если хук сам упал, вы всё равно получите
  `TokenExpired`, а тип сбоя хука будет в его заметке (`__notes__`) и в
  журнале.
- **http** (`httpx.AsyncClient` | `None`) — свой HTTP-клиент; его cookie-jar
  отключается, закрывать его — вам.

**Повторы.** Чтение при обрыве сети или ответе 502/503/504 повторяется один
раз. Запись — никогда; единственное исключение — `429` с коротким
`Retry-After`: сервис отказал до обработки, и повтор безопасен.

<a id="diarysdk.remote.RemoteDiary.login"></a>

#### *атрибут* `login`

[`RemoteLogin`](#diarysdk.remote.RemoteLogin).

<a id="diarysdk.remote.RemoteDiary.student"></a>

#### *метод* `student(token)`

Вернуть [`RemoteStudent`](#diarysdk.remote.RemoteStudent). Как
[`Diary.student()`](diarysdk.md#diarysdk.Diary.student).

<a id="diarysdk.remote.RemoteDiary.parent"></a>

#### *метод* `parent(token)`

Вернуть [`RemoteParent`](#diarysdk.remote.RemoteParent). Как
[`Diary.parent()`](diarysdk.md#diarysdk.Diary.parent).

*Добавлено в версии 0.2.0.*

<a id="diarysdk.remote.RemoteDiary.aclose"></a>

#### *async-метод* `aclose()`

Закрыть соединения. Свой `http=` остаётся открытым.

<a id="diarysdk.remote.RemoteLogin"></a>

### *класс* `diarysdk.remote.RemoteLogin`

Вход через сервис; методы — как у [`Login`](diarysdk.md#diarysdk.Login).
Ключу нужно [разрешение](server.md#разрешения-ключей) `login`, иначе
[`ForbiddenScope`](errors.md#diarysdk.errors.ForbiddenScope).

<a id="diarysdk.remote.RemoteLoginFlow"></a>

### *класс* `diarysdk.remote.RemoteLoginFlow`

Незаконченный вход через сервис; члены — как у
[`LoginFlow`](diarysdk.md#diarysdk.LoginFlow), включая `renew_captcha()` и
`close()`. Сам поток живёт на сервисе; клиент держит только его `flow_id`.

<a id="diarysdk.remote.RemoteStudent"></a>

### *класс* `diarysdk.remote.RemoteStudent`

Ученик через сервис; методы — как у [`Student`](diarysdk.md#diarysdk.Student).
Токен уходит в `Authorization: Bearer`, ученик родителя — параметром
`child_id`.

<a id="diarysdk.remote.RemoteParent"></a>

### *класс* `diarysdk.remote.RemoteParent`

Родитель через сервис; методы — как у [`Parent`](diarysdk.md#diarysdk.Parent).
`acknowledge_journal()` требует у ключа разрешения `acknowledge_journal`,
`update_contact()` — `write_profile`.

*Добавлено в версии 0.2.0.*

## Отличия от ядра

То, что видит вызывающий код:

- **Сеть.** Не дошли до сервиса или не дождались ответа —
  [`NetworkError`](errors.md#diarysdk.errors.NetworkError); запись при
  обрыве — [`WriteUncertain`](errors.md#diarysdk.errors.WriteUncertain).
- **Ключ.** Ключ не принят — [`BadApiKey`](errors.md#diarysdk.errors.BadApiKey),
  ключу не хватает разрешения —
  [`ForbiddenScope`](errors.md#diarysdk.errors.ForbiddenScope).
- **Контракт.** Ответ сервиса не по контракту —
  [`RemoteError`](errors.md#diarysdk.errors.RemoteError).
- **Атрибуты исключений.** У исключений заполнен `status` (HTTP-статус
  сервиса); `NotForRole.role`, `UnsupportedStep.what` и `hint` по HTTP не
  передаются.
- **Лимиты.** Сервис ограничивает запросы на ключ; см.
  [Лимиты](server.md#лимиты).
