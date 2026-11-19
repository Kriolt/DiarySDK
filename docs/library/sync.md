# `diarysdk.sync` — синхронные обёртки

[Документация](../index.md) » [Справочник библиотеки](index.md) » `diarysdk.sync`

**Исходный код:** [`diarysdk/sync.py`](../../diarysdk/sync.py),
типы — [`diarysdk/sync.pyi`](../../diarysdk/sync.pyi)

---

Те же `Diary` и `RemoteDiary`, но без `async` и `await` — для скриптов,
Django, Flask и прочего синхронного кода.

```python
from diarysdk.sync import RemoteDiary

with RemoteDiary("https://diarysdk.example", "my-api-key") as api:
    student = api.student("eyJ...")
    print(student.school().name)
```

<a id="diarysdk.sync.Diary"></a>

### *класс* `diarysdk.sync.Diary(*, hosts=None, timeout=15.0, deadline=20.0, http=None)`

Синхронный [`diarysdk.Diary`](diarysdk.md#diarysdk.Diary): те же параметры и
методы. Используйте как `with Diary() as api` или закрывайте
[`close()`](#diarysdk.sync.Diary.close).

<a id="diarysdk.sync.RemoteDiary"></a>

### *класс* `diarysdk.sync.RemoteDiary(base_url, api_key, *, timeout=30.0, max_rate_wait=2.0, on_token_expired=None, http=None)`

Синхронный [`diarysdk.remote.RemoteDiary`](remote.md#diarysdk.remote.RemoteDiary).

<a id="diarysdk.sync.Diary.close"></a>

#### *метод* `close()`

Закрыть соединения и остановить поток экземпляра. Есть у обоих классов; вместо
`aclose()` async-версий.

<a id="diarysdk.sync.Login"></a>

### *класс* `diarysdk.sync.Login`

<a id="diarysdk.sync.LoginFlow"></a>

### *класс* `diarysdk.sync.LoginFlow`

<a id="diarysdk.sync.Student"></a>

### *класс* `diarysdk.sync.Student`

<a id="diarysdk.sync.Parent"></a>

### *класс* `diarysdk.sync.Parent`

Синхронные [`Login`](diarysdk.md#diarysdk.Login),
[`LoginFlow`](diarysdk.md#diarysdk.LoginFlow),
[`Student`](diarysdk.md#diarysdk.Student) и
[`Parent`](diarysdk.md#diarysdk.Parent) — их возвращают `api.login`,
`api.student()`, `api.parent()` и шаги входа. Методы те же, без `await`.

## Как это работает

Каждый экземпляр `sync.Diary` или `sync.RemoteDiary` запускает свой поток с
циклом событий (имя потока — `diarysdk-sync`) и отправляет в него корутины
async-версии. Исключения доходят без изменений. Типы лежат в
`diarysdk/sync.pyi`: IDE и mypy видят настоящие сигнатуры.

> [!WARNING]
> Вызов **блокирует вызывающий поток**. Если сделать его из работающего цикла
> событий (async-функция, Jupyter), он заблокирует и этот цикл на время
> запроса. В async-коде пользуйтесь async-классами.

> [!WARNING]
> Финализатора нет. Поток — демон, и незакрытый экземпляр живёт вместе с
> соединениями до конца процесса. Закрывайте экземпляр через `with` или
> `close()`.

Вызов синхронного метода из хука `on_token_expired` того же экземпляра —
`RuntimeError`: хук выполняется внутри потока экземпляра.
