# DiarySDK

Python-библиотека для школьного дневника «Моя школа» (Московская область):
данные ученика по его токену или токену родителя — оценки, расписание,
домашние задания, рейтинг, учебный план, справки, настройки, профиль. Её же можно запустить как HTTP-сервис и ходить
в дневник через него.

Три части в одном пакете:

- **ядро** (`diarysdk.Diary`) — прямой доступ к дневнику, async;
- **удалённый клиент** (`diarysdk.remote.RemoteDiary`) — тот же интерфейс, но
  запросы идут в сервис DiarySDK;
- **сервис** (`python -m diarysdk.server`) — HTTP API над ядром с ключами
  потребителей, лимитами и журналом.

У ядра и удалённого клиента одинаковые методы, сигнатуры и исключения: код,
написанный под один, работает с другим. Синхронные версии лежат в
`diarysdk.sync`.

## Ограничение: нужен российский адрес

Дневник и Госуслуги отвечают только на запросы с российских IP-адресов.
Ядро (`Diary`) и сервис нужно запускать там, откуда дневник доступен. Удалённый
клиент ходит только в ваш сервис, ему такой адрес не нужен.

## Установка

Требуется Python 3.15 или новее.

```sh
pip install "diarysdk @ git+https://github.com/Kriolt/DiarySDK@v0.2.0"
# с сервисом (FastAPI, uvicorn):
pip install "diarysdk[server] @ git+https://github.com/Kriolt/DiarySDK@v0.2.0"
```

Зависимости ядра: `httpx`, `pydantic`, `tzdata`. Ядро не требует FastAPI.

## Быстрый старт напрямую

Токен ученика (JWT дневника) у вас уже есть; как его получить — в разделе
«Вход». Из токена `Diary` берёт ученика сам:

<!-- test -->
```python
import asyncio
import os

from diarysdk import Diary


async def main() -> None:
    async with Diary() as api:
        student = api.student(os.environ["DIARY_TOKEN"])
        print((await student.school()).name)
        for mark in await student.marks():
            print(mark.date, mark.subject.name, mark.value)
        for item in await student.homework():
            print(item.due, item.text, item.is_done)


asyncio.run(main())
```

`marks()`, `schedule()`, `homework()` и другие методы с периодом принимают
`start` и `end` (`datetime.date`); без них берётся разумный период по умолчанию
(см. [справочник](docs/library/diarysdk.md#diarysdk.Student)). Даты — по Москве.

## Быстрый старт через сервер

Тот же код, но класс другой и ему нужны адрес сервиса и ключ потребителя:

<!-- test -->
```python
import asyncio
import os

from diarysdk.remote import RemoteDiary


async def main() -> None:
    async with RemoteDiary("https://diarysdk.example", "my-api-key") as api:
        student = api.student(os.environ["DIARY_TOKEN"])
        print((await student.school()).name)
        print(len(await student.marks()), "оценок")


asyncio.run(main())
```

### Синхронный вариант

В `diarysdk.sync` те же `Diary` и `RemoteDiary`, но без `async`/`await`:

<!-- test -->
```python
import os

from diarysdk.sync import RemoteDiary

with RemoteDiary("https://diarysdk.example", "my-api-key") as api:
    student = api.student(os.environ["DIARY_TOKEN"])
    print(student.school().name)
    print(len(student.marks()), "оценок")
```

Каждый синхронный экземпляр держит свой поток с циклом событий. Вызов
**блокирует вызывающий поток**; если вызвать его из async-функции (или из
Jupyter), он заблокирует и её цикл событий на время запроса. В async-коде
пользуйтесь async-классами. Исключения доходят без изменений.

Полные примеры: [`examples/direct.py`](examples/direct.py),
[`examples/sync_remote.py`](examples/sync_remote.py),
[`examples/bot_flow.py`](examples/bot_flow.py) (бот целиком: вход, хранение
токена, чтение, запись, повторный вход).

## Родитель

Токен родителя открывает его собственные данные и всех его учеников:

<!-- test -->
```python
import asyncio
import os

from diarysdk import Diary


async def main() -> None:
    async with Diary() as api:
        parent = api.parent(os.environ["DIARY_TOKEN"])
        for child in await parent.children():
            student = parent.student(child.id)
            print(child.first_name, len(await student.marks()), "оценок")


asyncio.run(main())
```

`parent.student(child_id)` — тот же `Student` со всеми методами. Кое-что
дневник отдаёт только самому ученику: через родителя `exams()`, `avatar()`
и отметка ДЗ дают `NotForRole`. Справки (`certificates()`), наоборот, —
только через родителя. У родителя есть `me()`, `identity()`, `avatar()`,
настройки, своя почта и отметка «ознакомлен с дневником»
(`journal_acks`, `acknowledge_journal`; отметку видят учителя, отменить её
нельзя). Через сервис ученика выбирает параметр `child_id`. Подробно — в
[справочнике](docs/library/diarysdk.md#diarysdk.Parent).

## Вход

Токен ученика получают тремя способами. Любой из них даёт объект `Token`.

**1. Готовый JWT.** Вы уже знаете токен — передайте строку в
`api.student(token)` или оберните её: `Token("eyJ...")`. Срок читается из
самого токена; если токен не JWT или `exp` в нём нет, `Token.expires_at` равен
`None` (срок неизвестен, это не ошибка: дневник сам откажет, если токен плох).

**2. Логин и пароль дневника.**

<!-- test -->
```python
import asyncio

from diarysdk.remote import RemoteDiary


async def main() -> None:
    async with RemoteDiary("https://diarysdk.example", "my-api-key") as api:
        token = await api.login.password("login", "password")
        print(token.method, token.expires_at is not None)


asyncio.run(main())
```

**3. Госуслуги (ЕСИА).** Госуслуги могут потребовать капчу и код из
сообщения, поэтому `login.esia` возвращает либо `Token`, либо `LoginFlow` —
вход, который ждёт ответа. Поток живёт 5 минут с последнего шага.

<!-- test -->
```python
import asyncio

from diarysdk import Token
from diarysdk.remote import RemoteDiary


async def main() -> None:
    async with RemoteDiary("https://diarysdk.example", "my-api-key") as api:
        result = await api.login.esia("login", "password")
        while not isinstance(result, Token):
            if result.kind == "captcha":
                # result.captcha.image — картинка (bytes): покажите её ученику.
                result = await result.answer_captcha(input("Капча: "))
            else:
                # result.mfa описывает, куда ушёл код (sms, totp, max).
                result = await result.submit_code(input("Код: "))
        print(result.method)


asyncio.run(main())
```

Неверный ответ (`BadCode`, `BadCaptcha`) не убивает вход: у исключения есть
`.flow` — тот же поток, готовый к следующей попытке (`.flow` бывает `None`,
если продолжить нельзя). Разбор всех случаев — в `examples/bot_flow.py`.

Пароли, коды и ответы капчи нигде не сохраняются и не попадают в `repr`,
исключения и журналы.

Через сервис вход разрешён не любому ключу: ключу нужно разрешение `login`
(см. «Сервер»). Старты входа ограничены (5 в минуту на ключ).

## Хранение токена

SDK **не хранит токены**: это забота вашего приложения. Токен — секрет, его
`repr` и `str` показывают только метод, срок и короткую метку хеша, а значение
отдаётся явно через `token.value`. Сохраните значение и срок, потом
восстановите `Token`:

<!-- test -->
```python
from datetime import UTC, datetime, timedelta

from diarysdk import Token

token = Token("значение-токена", datetime.now(UTC) + timedelta(hours=8), method="esia")

row = {"value": token.value, "expires_at": token.expires_at, "method": token.method}
restored = Token(row["value"], row["expires_at"], row["method"])

print(restored == token)  # сравнение значений идёт за постоянное время
if restored.is_expiring():  # осталось меньше 5 минут или уже истёк
    print("пора входить заново")
```

`Token.expires_at` может быть `None`; тогда `expires_in()` возвращает `None`, а
`is_expiring()` — `False`. Токен, срок которого вышел, дневник отклонит
(`TokenExpired`), не дожидаясь запроса к нему.

У удалённого клиента есть хук `on_token_expired`: он вызывается один раз на
каждый отказ `token_expired` и получает `Token` (синхронная или async-функция).

## Запись и `WriteUncertain`

Писать можно: отметку «выполнено» у домашнего задания
(`homework_done`/`homework_undone`), настройки приложения (`update_settings`) и
почту в контактах (`update_contact`).

Если запись ушла, а ответа нет (обрыв сети, таймаут, 502/504 дневника), SDK
**не повторяет её** и бросает `WriteUncertain`: неизвестно, применил ли
дневник изменение. Перечитайте состояние и решите сами:

<!-- test -->
```python
import asyncio
import os

from diarysdk import WriteUncertain
from diarysdk.remote import RemoteDiary


async def main() -> None:
    async with RemoteDiary("https://diarysdk.example", "my-api-key") as api:
        student = api.student(os.environ["DIARY_TOKEN"])
        todo = [item for item in await student.homework() if not item.is_done]
        if todo:
            try:
                await student.homework_done(todo[0].id)
                print("отмечено")
            except WriteUncertain as error:
                print("исход неизвестен, причина:", error.cause.code)
                await student.homework()  # перечитать, не повторять вслепую


asyncio.run(main())
```

Через сервис запись правки контактов требует у ключа разрешения
`write_profile`.

## Ошибки

Все исключения — наследники `DiaryError`; у каждого есть `message` (по-русски,
без секретов), `status`, `retry_after` и стабильный машинный код в `code`.

| Класс | Когда | Что делать |
| --- | --- | --- |
| `AuthError` (`TokenInvalid`, `TokenExpired`, `BadCredentials`, `LoginBlocked`, `FlowExpired`, `BadCode`, `BadCaptcha`, `UnsupportedStep`) | токен или вход не приняты | звать ученика входить заново |
| `BadRequest`, `NotFound`, `NoAvatar`, `MultipleChildren`, `NotForRole` | запрос неверный или данных нет | исправить запрос |
| `SettingError` (`SettingsMissing`, `SettingNotSet`, `SettingUnrestorable`), `UnsupportedContact` | запись невозможна, не отправлена | не повторять без изменений |
| `RateLimited` | лимит запросов | подождать `retry_after` |
| `UpstreamError` (`UpstreamTimeout`, `UpstreamFormat`) | дневник недоступен или ответил непонятно | повторить позже |
| `WriteUncertain` | запись могла примениться | перечитать состояние |
| `RemoteError` (`BadApiKey`, `ForbiddenScope`, `NetworkError`) | только у удалённого клиента: сервис не достигнут или ключ не подходит | проверить адрес, сеть, ключ |

Обрыв сети до сервиса в удалённом клиенте — `NetworkError(RemoteError)`.
Полная таблица — в [справочнике](docs/library/errors.md#коды-ошибок-сервиса).

<!-- test -->
```python
import asyncio
import os

from diarysdk import NetworkError, RateLimited, TokenExpired, UpstreamError
from diarysdk.remote import RemoteDiary


async def main() -> None:
    async with RemoteDiary("https://diarysdk.example", "my-api-key") as api:
        student = api.student(os.environ["DIARY_TOKEN"])
        try:
            print(len(await student.marks()))
        except TokenExpired:
            print("ученику нужно войти заново")
        except RateLimited as error:
            print("слишком часто, повторите через", error.retry_after)
        except UpstreamError, NetworkError:
            print("дневник или сервис недоступен, попробуйте позже")


asyncio.run(main())
```

## Особенности

- **Журнал `httpx`.** При импорте SDK добавляет фильтр к глобальному логгеру
  `httpx`: он скрывает записи о наших запросах к дневнику (в URL бывают
  идентификаторы ученика). Остальные записи `httpx` и логи вашего приложения
  фильтр не трогает. Логгер `httpcore` фильтр **не** скрывает: на уровне
  DEBUG он пишет адреса и заголовки соединений, поэтому не включайте DEBUG
  для `httpcore` там, где логи уходят во внешние системы.
- **Свой `httpx.AsyncClient`.** Параметр `http=` принимает ваш клиент (прокси,
  тесты, свои таймауты). У него отключается cookie-jar: куки входа SDK ведёт
  сам, общий jar смешал бы сессии разных учеников. Чужой клиент SDK не
  закрывает.
- **Синхронные обёртки блокируют поток**, а при вызове из async-кода — и его
  цикл событий (см. выше). У `sync.Diary` и `sync.RemoteDiary` нет
  финализатора: незакрытый экземпляр оставляет поток-демон с соединениями до
  конца процесса, поэтому закрывайте его через `with` или `close()`.
- **Токен родителя с несколькими детьми** в `diary.student(token)` —
  `MultipleChildren`: выбирайте ребёнка через `diary.parent(token)`.

## Сервер

Запустите сервис там, где доступен дневник (российский адрес).

1. Выпустите ключ потребителя. Ключ покажется один раз в stderr, в stdout —
   строка для файла ключей (хранится только хеш):

   ```sh
   python -m diarysdk.server.keys new bot --scope login --scope write_profile >> api-keys
   ```

   Строка файла: `<имя> <sha256 ключа> [разрешения]`. Файл перечитывается при
   изменении, перезапуск не нужен.

2. Запустите:

   ```sh
   DIARYSDK_KEYS_FILE=./api-keys python -m diarysdk.server
   ```

   По умолчанию сервис слушает `127.0.0.1:8000`. Настройки — переменные
   `DIARYSDK_*` (таблица в [справочнике](docs/library/server.md#переменные-окружения)). Состояние здоровья:
   `GET /healthz`. Схема API: `/openapi.json`.

3. Клиенты передают ключ в `X-Api-Key`, токен ученика — в
   `Authorization: Bearer <токен>`.

Сервис держит лимит запросов на ключ (по умолчанию 10 в секунду, всплеск 30),
отдельный счётчик стартов входа и журнал запросов без секретов. TLS и
публикацию в сеть обеспечивает обратный прокси.

### Docker

```sh
docker build -t diarysdk .
docker run --rm -p 8000:8000 --read-only \
  -v "$PWD/api-keys:/etc/diarysdk/api-keys:ro" \
  diarysdk
```

Образ работает не от root (uid 10001), не пишет на диск и стартует с
`DIARYSDK_HOST=0.0.0.0`; путь к файлу ключей задаёт `DIARYSDK_KEYS_FILE`
(по умолчанию `/etc/diarysdk/api-keys` — смонтируйте файл только для чтения).
Проверка здоровья встроена (`/healthz`). Образы не публикуются: собирайте
сами.

## Документация

Полная документация — в [`docs/`](docs/index.md):

- [учебник](docs/tutorial/index.md) — по шагам от первого запроса до своего
  сервиса;
- [справочник библиотеки](docs/library/index.md) — каждый класс, метод,
  модель и исключение;
- [HTTP API](docs/http.md) — маршруты и коды ошибок сервиса;
- [глоссарий](docs/glossary.md) и [алфавитный указатель](docs/genindex.md);
- [устройство пакета](docs/architecture.md) — для тех, кто правит DiarySDK;
- [`CHANGELOG.md`](CHANGELOG.md), [`SECURITY.md`](SECURITY.md).

## Разработка

```sh
pip install -e '.[server,dev]'
ruff check . && ruff format --check . && pytest
python scripts/check_clean.py
```

Примеры в этом README и в `docs/` исполняются тестом `tests/test_docs.py` против
подставных транспортов, без сети. Указатель `docs/genindex.md` собирается
`python scripts/gen_doc_index.py`.

## Лицензия

MIT, правообладатель — Kriolt. См. [`LICENSE`](LICENSE).
