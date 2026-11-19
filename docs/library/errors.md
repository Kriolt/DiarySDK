# `diarysdk.errors` — исключения

[Документация](../index.md) » [Справочник библиотеки](index.md) » `diarysdk.errors`

**Исходный код:** [`diarysdk/errors.py`](../../diarysdk/errors.py)

---

Ядро, сервис и удалённый клиент бросают одни и те же исключения. Все они —
наследники [`DiaryError`](#diarysdk.errors.DiaryError) и импортируются из
корня пакета:

```python
from diarysdk import DiaryError, RateLimited, TokenExpired
```

В исключениях нет ни паролей, ни токенов, ни кодов входа, ни ответов капчи:
их можно писать в журнал. Сообщения — по-русски.

## Иерархия

```
DiaryError
 ├── AuthError
 │    ├── TokenInvalid
 │    ├── TokenExpired
 │    ├── BadCredentials
 │    ├── BadCode
 │    ├── BadCaptcha
 │    ├── FlowExpired
 │    ├── LoginBlocked
 │    └── UnsupportedStep
 ├── BadRequest
 ├── NotFound
 │    └── NoAvatar
 ├── MultipleChildren
 ├── NotForRole
 ├── SettingError
 │    ├── SettingsMissing
 │    ├── SettingNotSet
 │    └── SettingUnrestorable
 ├── UnsupportedContact
 ├── RateLimited
 ├── UpstreamError
 │    ├── UpstreamTimeout
 │    └── UpstreamFormat
 ├── WriteUncertain
 └── RemoteError
      ├── BadApiKey
      ├── ForbiddenScope
      └── NetworkError
```

## Что делать с ошибкой

| Исключение | Когда | Что делать |
| --- | --- | --- |
| [`AuthError`](#diarysdk.errors.AuthError) и подклассы | токен или вход не приняты | позвать пользователя входить заново |
| [`BadRequest`](#diarysdk.errors.BadRequest), [`NotFound`](#diarysdk.errors.NotFound), [`NoAvatar`](#diarysdk.errors.NoAvatar), [`MultipleChildren`](#diarysdk.errors.MultipleChildren), [`NotForRole`](#diarysdk.errors.NotForRole) | запрос неверный или данных нет | исправить запрос |
| [`SettingError`](#diarysdk.errors.SettingError) и подклассы, [`UnsupportedContact`](#diarysdk.errors.UnsupportedContact) | запись невозможна и не отправлена | не повторять без изменений |
| [`RateLimited`](#diarysdk.errors.RateLimited) | лимит запросов | подождать `retry_after` секунд |
| [`UpstreamError`](#diarysdk.errors.UpstreamError) и подклассы | дневник недоступен или ответил непонятно | повторить позже |
| [`WriteUncertain`](#diarysdk.errors.WriteUncertain) | запись могла примениться | перечитать состояние, не повторять вслепую |
| [`RemoteError`](#diarysdk.errors.RemoteError) и подклассы | только у удалённого клиента: сервис недоступен или ключ не подходит | проверить адрес, сеть, ключ |

## База

<a id="diarysdk.errors.DiaryError"></a>

### *исключение* `diarysdk.errors.DiaryError(message="", *, status=None, retry_after=None)`

База всех исключений SDK; сама бросается, когда дневник ответил ошибкой
другого рода. Пустое `message` заменяется текстом по умолчанию для класса.

<a id="diarysdk.errors.DiaryError.message"></a>

#### *атрибут* `message`

Текст по-русски, без секретов; то же, что `str(error)`.

<a id="diarysdk.errors.DiaryError.code"></a>

#### *атрибут* `code`

Стабильный машинный код класса, например `"token_expired"`. Это же значение —
поле `error` в теле ответа сервиса.

<a id="diarysdk.errors.DiaryError.raw_code"></a>

#### *атрибут* `raw_code`

Код, как его прислал сервис. Отличается от `code`, когда класс выбран по
HTTP-статусу (неизвестный код или ответ прокси): тогда это сам код или
`"http_<статус>"`.

<a id="diarysdk.errors.DiaryError.status"></a>

#### *атрибут* `status`

HTTP-статус ответа сервиса, если клиент его получил; у ядра — `None`.

<a id="diarysdk.errors.DiaryError.retry_after"></a>

#### *атрибут* `retry_after`

Через сколько секунд можно повторить (`float`), если известно.

<a id="diarysdk.errors.DiaryError.http_status"></a>

#### *атрибут класса* `http_status`

HTTP-статус, которым сервис отвечает на это исключение.

## Вход и токен

<a id="diarysdk.errors.AuthError"></a>

### *исключение* `diarysdk.errors.AuthError`

Токен или вход пользователя не приняты: нужно звать пользователя. Код
`auth_error`, HTTP 401.

<a id="diarysdk.errors.TokenInvalid"></a>

### *исключение* `diarysdk.errors.TokenInvalid`

Дневник не принял токен, или это вовсе не JWT дневника. Код `token_invalid`
(а также `token_missing` — у сервиса нет заголовка `Authorization`), HTTP 401.

<a id="diarysdk.errors.TokenExpired"></a>

### *исключение* `diarysdk.errors.TokenExpired`

Срок токена вышел. Код `token_expired`, HTTP 401. Ядро бросает его, не
обращаясь к дневнику (см. [`Token.ensure_usable()`](token.md#diarysdk.Token.ensure_usable)).

<a id="diarysdk.errors.BadCredentials"></a>

### *исключение* `diarysdk.errors.BadCredentials`

Неверный логин или пароль. Код `bad_credentials`, HTTP 401.

<a id="diarysdk.errors.BadCode"></a>

### *исключение* `diarysdk.errors.BadCode`

Неверный код подтверждения. Код `bad_code`, HTTP 401. Вход при этом жив.

<a id="diarysdk.errors.BadCode.flow"></a>

#### *атрибут* `flow`

Тот же [`LoginFlow`](diarysdk.md#diarysdk.LoginFlow), готовый к следующей
попытке; `None`, если продолжить нельзя.

<a id="diarysdk.errors.BadCode.step"></a>

#### *атрибут* `step`

Обновлённый шаг: оставшиеся попытки или новая капча. У удалённого клиента —
[`LoginStep`](models.md#diarysdk.models.LoginStep) из тела ответа.

<a id="diarysdk.errors.BadCaptcha"></a>

### *исключение* `diarysdk.errors.BadCaptcha`

Неверный ответ на капчу. Код `bad_captcha`, HTTP 401. Атрибуты `flow` и
`step` — как у [`BadCode`](#diarysdk.errors.BadCode); в `step` — свежая
капча.

```python
try:
    result = await flow.answer_captcha(answer)
except BadCaptcha as error:
    if error.flow is None:
        raise
    flow = error.flow  # показать пользователю error.flow.captcha.image
```

<a id="diarysdk.errors.FlowExpired"></a>

### *исключение* `diarysdk.errors.FlowExpired`

Вход не найден, истёк (5 минут без шага) или закрыт. Код `flow_expired`, HTTP
404. Начните вход заново.

<a id="diarysdk.errors.LoginBlocked"></a>

### *исключение* `diarysdk.errors.LoginBlocked`

Госуслуги или портал заблокировали вход, или попытки кончились. Код
`login_blocked`, HTTP 409. Попробуйте позже или передайте готовый JWT.

<a id="diarysdk.errors.UnsupportedStep"></a>

### *исключение* `diarysdk.errors.UnsupportedStep`

Госуслуги просят шаг, которого SDK не умеет. Код `unsupported_step`, HTTP
422.

<a id="diarysdk.errors.UnsupportedStep.what"></a>

#### *атрибут* `what`

Название шага (уже очищенное от данных пользователя); у ядра.

<a id="diarysdk.errors.UnsupportedStep.hint"></a>

#### *атрибут* `hint`

Совет, что делать; у ядра. По HTTP `what` и `hint` уходят только внутри
`message`.

## Запрос и данные

<a id="diarysdk.errors.BadRequest"></a>

### *исключение* `diarysdk.errors.BadRequest`

Неверные параметры: начало периода позже конца, слишком длинный период, не
адрес почты, `child_id <= 0`. Код `bad_request`, HTTP 400. Значения параметров
в сообщение не попадают.

<a id="diarysdk.errors.NotFound"></a>

### *исключение* `diarysdk.errors.NotFound`

В дневнике такого нет: оценки, урока, предмета, контакта, ученика у родителя.
Код `not_found`, HTTP 404.

<a id="diarysdk.errors.NoAvatar"></a>

### *исключение* `diarysdk.errors.NoAvatar`

Аватарки нет. Подкласс [`NotFound`](#diarysdk.errors.NotFound); код
`no_avatar`, HTTP 404.

<a id="diarysdk.errors.MultipleChildren"></a>

### *исключение* `diarysdk.errors.MultipleChildren`

Токен родителя с несколькими детьми передан в
[`Diary.student()`](diarysdk.md#diarysdk.Diary.student): непонятно, чьи
данные нужны. Код `multiple_children`, HTTP 422. Выбирайте ребёнка через
`diary.parent(token).student(child_id)`, а у сервиса — параметром `child_id`.

<a id="diarysdk.errors.NotForRole"></a>

### *исключение* `diarysdk.errors.NotForRole`

Для этой роли дневник эти данные не отдаёт: через родителя — `exams()`,
`avatar()` ученика и отметку ДЗ; ученику — справки; токен не родителя в
`Diary.parent()`. Код `not_for_role`, HTTP 422. Ядро бросает его до запроса к
дневнику.

*Добавлено в версии 0.2.0.*

<a id="diarysdk.errors.NotForRole.role"></a>

#### *атрибут* `role`

`"student"` или `"parent"` — роль токена. Есть только у ядра: по HTTP
передаются лишь код и текст, у удалённого клиента `role` равно `None`.

## Запись

<a id="diarysdk.errors.SettingError"></a>

### *исключение* `diarysdk.errors.SettingError`

Настройку записать нельзя; запись не отправлялась. Код `setting_error`, HTTP
409.

<a id="diarysdk.errors.SettingsMissing"></a>

### *исключение* `diarysdk.errors.SettingsMissing`

Группы настроек приложения в дневнике нет: записывать некуда, а создать её
SDK не может. Код `settings_missing`, HTTP 409.

<a id="diarysdk.errors.SettingNotSet"></a>

### *исключение* `diarysdk.errors.SettingNotSet`

У настройки в дневнике нет значения. Код `setting_unset`, HTTP 409.

<a id="diarysdk.errors.SettingNotSet.field"></a>

#### *атрибут* `field`

Имя поля из вашего запроса (`"theme.type"`); есть и у
[`SettingUnrestorable`](#diarysdk.errors.SettingUnrestorable).

<a id="diarysdk.errors.SettingUnrestorable"></a>

### *исключение* `diarysdk.errors.SettingUnrestorable`

Текущее значение настройки вне известных SDK: записав новое, вернуть прежнее
было бы нечем. Код `setting_unrestorable`, HTTP 409.

<a id="diarysdk.errors.UnsupportedContact"></a>

### *исключение* `diarysdk.errors.UnsupportedContact`

Контакт — не адрес почты, а SDK правит только почту. Код `contact_not_email`,
HTTP 422.

<a id="diarysdk.errors.WriteUncertain"></a>

### *исключение* `diarysdk.errors.WriteUncertain(message="", *, cause, status=None, retry_after=None)`

Запись ушла, но ответа нет — обрыв сети, таймаут, 502/504 дневника или
дедлайн вызова. Применил ли дневник изменение, неизвестно. SDK **не
повторяет** запись: перечитайте состояние и решите сами.

`code` и `http_status` повторяют причину. Определённый отказ дневника на
записи (400, 401, 403, 500) — обычная ошибка, а не `WriteUncertain`.

```python
try:
    await student.homework_done(item.id)
except WriteUncertain:
    fresh = await student.homework()  # перечитать, а не повторять вслепую
```

<a id="diarysdk.errors.WriteUncertain.cause"></a>

#### *атрибут* `cause`

Причина: [`UpstreamError`](#diarysdk.errors.UpstreamError),
[`UpstreamTimeout`](#diarysdk.errors.UpstreamTimeout) или
[`NetworkError`](#diarysdk.errors.NetworkError).

<a id="diarysdk.errors.WriteUncertain.upstream_status"></a>

#### *свойство* `upstream_status`

Статус ответа дневника, если он известен; `401` и `403` значат, что запись
точно не прошла.

## Лимиты и дневник

<a id="diarysdk.errors.RateLimited"></a>

### *исключение* `diarysdk.errors.RateLimited`

Слишком много запросов. Код `rate_limited`, HTTP 429; через сколько секунд
повторить — в `retry_after` (и в заголовке `Retry-After`).

<a id="diarysdk.errors.UpstreamError"></a>

### *исключение* `diarysdk.errors.UpstreamError`

Дневник недоступен или ответил ошибкой: повторите позже. Код `upstream_error`,
HTTP 502.

<a id="diarysdk.errors.UpstreamError.upstream_status"></a>

#### *атрибут* `upstream_status`

Статус, которым ответил дневник; `None` — до него не достучались.

<a id="diarysdk.errors.UpstreamTimeout"></a>

### *исключение* `diarysdk.errors.UpstreamTimeout`

Дневник не ответил вовремя (`timeout` запроса или `deadline` вызова). Код
`upstream_timeout`, HTTP 504.

<a id="diarysdk.errors.UpstreamFormat"></a>

### *исключение* `diarysdk.errors.UpstreamFormat`

Ответ дневника не разобрался: другая форма, `null` вместо списка, поле другого
типа. Код `upstream_format`, HTTP 502.

<a id="diarysdk.errors.UpstreamFormat.problems"></a>

#### *атрибут* `problems`

Список строк «путь поля: тип ошибки». Значений полей в нём нет — там могли
быть чьи-то ФИО.

## Удалённый клиент

Эти исключения бросает только [`RemoteDiary`](remote.md#diarysdk.remote.RemoteDiary).

<a id="diarysdk.errors.RemoteError"></a>

### *исключение* `diarysdk.errors.RemoteError`

Сервис не ответил как ожидалось: ответ не по контракту. Код `remote_error`,
HTTP 502.

<a id="diarysdk.errors.BadApiKey"></a>

### *исключение* `diarysdk.errors.BadApiKey`

Ключ `X-Api-Key` неверный или отсутствует. Код `bad_api_key`, HTTP 403.

<a id="diarysdk.errors.ForbiddenScope"></a>

### *исключение* `diarysdk.errors.ForbiddenScope`

Ключу не разрешена эта операция: нет нужного
[разрешения](server.md#разрешения-ключей). Код `forbidden_scope`, HTTP 403.

<a id="diarysdk.errors.NetworkError"></a>

### *исключение* `diarysdk.errors.NetworkError`

До сервиса не дошли или не дождались ответа. Своего кода в ответе нет: это
ошибка самого клиента. Запись при обрыве — не `NetworkError`, а
[`WriteUncertain`](#diarysdk.errors.WriteUncertain) с `NetworkError` в `cause`.

## Коды ошибок сервиса

Тело ошибки сервиса: `{"error": <код>, "message": <текст>}`. Удалённый клиент
превращает код в класс по этой таблице.

| Код (`error`) | Класс | HTTP | Смысл |
| --- | --- | --- | --- |
| `diary_error` | `DiaryError` | 502 | дневник ответил ошибкой |
| `auth_error` | `AuthError` | 401 | токен или вход не приняты |
| `token_invalid` | `TokenInvalid` | 401 | дневник не принял токен |
| `token_missing` | `TokenInvalid` | 401 | нет заголовка `Authorization` |
| `token_expired` | `TokenExpired` | 401 | срок токена вышел |
| `bad_credentials` | `BadCredentials` | 401 | неверный логин или пароль |
| `bad_code` | `BadCode` | 401 | неверный код; в теле — новый `step` |
| `bad_captcha` | `BadCaptcha` | 401 | неверная капча; в теле — новый `step` |
| `flow_expired` | `FlowExpired` | 404 | вход не найден или истёк |
| `login_blocked` | `LoginBlocked` | 409 | вход заблокирован |
| `unsupported_step` | `UnsupportedStep` | 422 | шаг Госуслуг, которого нет в SDK |
| `bad_request` | `BadRequest` | 400 | неверные параметры |
| `not_found` | `NotFound` | 404 | в дневнике такого нет |
| `no_avatar` | `NoAvatar` | 404 | аватарки нет |
| `multiple_children` | `MultipleChildren` | 422 | у родителя несколько детей: нужен `child_id` |
| `not_for_role` | `NotForRole` | 422 | для этой роли данных нет |
| `setting_error` | `SettingError` | 409 | настройку записать нельзя |
| `settings_missing` | `SettingsMissing` | 409 | настроек приложения нет |
| `setting_unset` | `SettingNotSet` | 409 | у настройки нет значения |
| `setting_unrestorable` | `SettingUnrestorable` | 409 | текущее значение не вернуть |
| `contact_not_email` | `UnsupportedContact` | 422 | контакт не почта |
| `rate_limited` | `RateLimited` | 429 | лимит; заголовок `Retry-After` |
| `upstream_error` | `UpstreamError` | 502 | дневник недоступен; в теле `upstream_status` |
| `upstream_timeout` | `UpstreamTimeout` | 504 | дневник не ответил вовремя |
| `upstream_format` | `UpstreamFormat` | 502 | ответ дневника не разобрался |
| `remote_error` | `RemoteError` | 502 | ответ не по контракту |
| `bad_api_key` | `BadApiKey` | 403 | ключ не принят |
| `forbidden_scope` | `ForbiddenScope` | 403 | у ключа нет разрешения |

Неизвестный код (ответ прокси или новый код более нового сервера) разбирается
по статусу: 401 — `AuthError`, 403 — `RemoteError`, 404 — `NotFound`, 429 —
`RateLimited`, 5xx — `UpstreamError`, остальное — `DiaryError`. Поэтому новый
сервер не ломает старый клиент.

`WriteUncertain` своего кода не имеет: сервис отвечает кодом и статусом
причины и добавляет в тело `"uncertain": true`. Клиент строит
`WriteUncertain` из обрыва связи, из ответа 502/504 с `"uncertain": true` или
из 502/504 не от сервиса (тело не JSON сервиса, как у прокси).

## Функции

Нужны тем, кто пишет свой сервер или клиент поверх контракта.

<a id="diarysdk.errors.to_response"></a>

### *функция* `diarysdk.errors.to_response(error)`

Вернуть пару `(status, body)` для ответа сервиса на исключение `error`.

<a id="diarysdk.errors.from_response"></a>

### *функция* `diarysdk.errors.from_response(status, body, retry_after=None)`

Разобрать ответ сервиса с ошибкой в исключение. Тело не по форме (ответ
прокси) разбор не роняет.

<a id="diarysdk.errors.BY_CODE"></a>

### *атрибут* `diarysdk.errors.BY_CODE`

Словарь «код → класс» из таблицы выше.
