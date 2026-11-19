# `diarysdk.server` — HTTP-сервис

[Документация](../index.md) » [Справочник библиотеки](index.md) » `diarysdk.server`

**Исходный код:** [`diarysdk/server/`](../../diarysdk/server/)

---

Сервис — HTTP API над [ядром](diarysdk.md) на FastAPI: ключи потребителей с
разрешениями, лимиты запросов и журнал без секретов. Ходить в него удобно
через [`RemoteDiary`](remote.md#diarysdk.remote.RemoteDiary); маршруты описаны
в [HTTP API](../http.md).

Сервису нужны зависимости из extra `server`:

```sh
pip install "diarysdk[server] @ git+https://github.com/Kriolt/DiarySDK@v0.2.0"
```

> [!IMPORTANT]
> Запускайте сервис там, откуда доступен дневник, — с российского адреса. TLS
> и публикацию в сеть обеспечивает обратный прокси перед сервисом.

## Запуск

```sh
DIARYSDK_KEYS_FILE=./api-keys python -m diarysdk.server
```

По умолчанию сервис слушает `127.0.0.1:8000`. Проверка здоровья —
`GET /healthz`, схема API — `/openapi.json` (интерактивно — `/docs`).

### Переменные окружения

| Переменная | По умолчанию | Что значит |
| --- | --- | --- |
| `DIARYSDK_KEYS_FILE` | — (обязательна) | файл ключей; без него сервис не стартует |
| `DIARYSDK_HOST` | `127.0.0.1` | адрес, который слушает сервис |
| `DIARYSDK_PORT` | `8000` | порт |
| `DIARYSDK_RATE_PER_SECOND` | `10` | жетонов в секунду на ключ |
| `DIARYSDK_RATE_BURST` | `30` | запас жетонов (всплеск) |
| `DIARYSDK_VERSION` | версия пакета | версия сборки; отдаётся в `X-App-Version` у `/healthz` |
| `DIARYSDK_DNEVNIK_URL` | `https://authedu.mosreg.ru` | хост дневника |
| `DIARYSDK_SCHOOL_API_URL` | `https://authedu.mosreg.ru/api` | API школы |
| `DIARYSDK_SCHOOL_URL` | `https://myschool.mosreg.ru` | портал |
| `DIARYSDK_ESIA_URL` | `https://esia.gosuslugi.ru` | Госуслуги |

Нет файла ключей или не разобралось число — ошибка старта (`ConfigError`).

## Ключи потребителей

Каждый потребитель (бот, сайт, скрипт) получает свой ключ и передаёт его в
заголовке `X-Api-Key`. Сам ключ сервис не хранит — только его SHA-256.

### Выпуск ключа

```sh
python -m diarysdk.server.keys new <имя> [--scope login] [--scope write_profile] [--scope acknowledge_journal] >> api-keys
```

Ключ печатается один раз в stderr, строка для файла — в stdout. Флаг
`--scope` повторяется — по одному на разрешение. Имя потребителя — латиница,
цифры и `_.-`; по нему считаются лимиты и пишется журнал.

### Файл ключей

Одна строка на ключ:

```
<имя> <sha256 ключа> [разрешения через запятую]
```

Пустые строки и строки с `#` пропускаются; строка не по формату пропускается с
предупреждением в журнале (без её содержимого). Файл перечитывается при
изменении — не чаще раза в 10 секунд, перезапуск не нужен.

### Разрешения ключей

Без разрешений ключ открывает чтение и обычную запись (отметку ДЗ,
настройки). Остальное — по разрешениям:

| Разрешение | Что открывает |
| --- | --- |
| `login` | `/v1/auth/*` (кроме `GET /v1/auth/token`): вход по паролю и через Госуслуги |
| `write_profile` | `PUT /v1/identity/contacts/{id}`, `PUT /v1/parent/identity/contacts/{id}` |
| `acknowledge_journal` | `POST /v1/parent/journal-acks` |

Нет нужного разрешения — `403 forbidden_scope`
([`ForbiddenScope`](errors.md#diarysdk.errors.ForbiddenScope)).

## Лимиты

- **Общий лимит** — ведро жетонов на потребителя
  (`DIARYSDK_RATE_PER_SECOND`, `DIARYSDK_RATE_BURST`). Превышение —
  `429 rate_limited` с заголовком `Retry-After`.
- **Старты входа** (`POST /v1/auth/password`, `POST /v1/auth/esia`) — отдельно,
  5 в минуту на потребителя.
- **Одновременные входы через Госуслуги** — не больше 3 на потребителя и 100
  всего; при исчерпании — `429`.

## Журнал

Журнал запросов — JSON-строки в stdout: метод, путь, статус, время, число
запросов к дневнику. Заголовки, тела, токены и значения параметров в журнал
не пишутся.

## Docker

Образ собирается из `Dockerfile` в корне репозитория; готовые образы не
публикуются.

```sh
docker build -t diarysdk .
docker run --rm -p 8000:8000 --read-only \
  -v "$PWD/api-keys:/etc/diarysdk/api-keys:ro" \
  diarysdk
```

Образ: Python 3.15, пользователь не root (uid 10001), `DIARYSDK_HOST=0.0.0.0`,
файл ключей — `DIARYSDK_KEYS_FILE=/etc/diarysdk/api-keys` (монтируйте его
только для чтения), встроенная проверка здоровья по `/healthz`. На диск
сервис не пишет, поэтому работает с `--read-only`.
