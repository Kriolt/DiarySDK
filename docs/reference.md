# Справочник DiarySDK

Идентификаторы — английские, пояснения — русские. Даты — `datetime.date`,
время — с часовым поясом; «сегодня» считается по Москве.

- [Корневой пакет и классы](#корневой-пакет-и-классы)
- [Вход: Login и LoginFlow](#вход-login-и-loginflow)
- [Student: методы](#student-методы)
- [Token](#token)
- [Удалённый клиент](#удалённый-клиент-diarysdkremote)
- [Синхронные обёртки](#синхронные-обёртки-diarysdksync)
- [Протоколы](#протоколы)
- [Модели](#модели)
- [Исключения](#исключения)
- [Сервер: запуск и настройки](#сервер-запуск-и-настройки)
- [HTTP-контракт](#http-контракт)

## Корневой пакет и классы

Из `diarysdk` импортируются все публичные имена (`diarysdk.__all__`):

- ядро: `Diary`, `Login`, `LoginFlow`, `Student`, `Token`, `Hosts`;
- протоколы: `DiaryLike`, `LoginLike`, `LoginFlowLike`, `StudentLike`;
- модели входа и данные: `Avatar`, `Captcha`, `LoginMfa`, `TokenInfo` (ответ
  `GET /v1/auth/token`; из ядра его не возвращает ничто — срок, субъект и роли
  читаются у `Token`);
- исключения: см. [Исключения](#исключения);
- `__version__` — версия пакета (`"0.1.0"`).

Все остальные модели собраны в `diarysdk.models` (`from diarysdk.models import
Homework, Mark, ...`; список — `diarysdk.models.__all__`) и лежат в
`diarysdk.models.<модуль>`.

### `Diary(*, hosts=None, timeout=15.0, deadline=20.0, http=None)`

Прямой доступ к дневнику (async). Используйте как `async with Diary() as api`
или закрывайте `await api.aclose()`.

| Параметр | Что значит |
| --- | --- |
| `hosts` | `Hosts` с адресами хостов дневника и Госуслуг (по умолчанию — боевые) |
| `timeout` | секунд на один запрос к дневнику |
| `deadline` | секунд на весь вызов (контекст ученика, чтение, повтор) |
| `http` | свой `httpx.AsyncClient`; см. ниже |

- `api.login` — [`Login`](#вход-login-и-loginflow);
- `api.student(token)` — [`Student`](#student-методы); `token` — `str` или `Token`;
- `await api.aclose()` — закрыть соединения и незаконченные входы.
  Вызов после закрытия — `RuntimeError`.

**Свой `http=`.** Переданный `httpx.AsyncClient` SDK не закрывает; у него
отключается cookie-jar (куки входа SDK ведёт сам: общий jar смешал бы сессии
разных учеников). Это относится и к `RemoteDiary`.

**Журнал.** При импорте SDK добавляет фильтр к глобальному логгеру `httpx`:
скрываются записи о запросах к дневнику (URL содержит идентификаторы ученика).
Другие записи `httpx` фильтр не трогает.

### `Hosts(dnevnik, school_api, school, esia)`

Неизменяемый набор адресов: дневник (`https://authedu.mosreg.ru`), API школы
(`https://authedu.mosreg.ru/api`), портал (`https://myschool.mosreg.ru`),
Госуслуги (`https://esia.gosuslugi.ru`, только для входа). Меняется в тестах и
за прокси.

### `DiaryFile(content, content_type, filename)`

Файл от дневника (PDF итоговых): байты, тип и имя для сохранения; из `diarysdk.models`.

### `Avatar(content, content_type)`

Результат `Student.avatar()`: байты картинки и её MIME-тип.

## Вход: Login и LoginFlow

`api.login` — объект `Login`:

| Метод | Возвращает | Заметки |
| --- | --- | --- |
| `await login.password(login, password)` | `Token` (`method="password"`) | вход по логину и паролю дневника |
| `await login.esia(login, password)` | `Token` (`method="esia"`) или `LoginFlow` | Госуслуги; `LoginFlow`, если нужен код или капча |

`LoginFlow` — вход, который ждёт ответа:

| Член | Что это |
| --- | --- |
| `kind` | `"mfa"` (ждёт код) или `"captcha"` (ждёт ответ на капчу) |
| `mfa` | `LoginMfa` или `None`: `kind` (`sms`/`totp`/`max`), `contact` (скрыт из `repr`), `ttl`, `attempts_left` |
| `captcha` | `Captcha` или `None`: `kind` (`image`/`question`), `image` (bytes), `image_type`, `question` |
| `expires_at` | когда поток истечёт (5 минут с последнего шага) |
| `await submit_code(code)` | `Token` или следующий `LoginFlow` |
| `await answer_captcha(answer)` | `Token` или следующий `LoginFlow` |
| `await renew_captcha()` | `LoginFlow` со свежей капчей |
| `await close()` | отменить вход; повторный вызов не ошибка |

Неверный ответ — `BadCode`/`BadCaptcha`: у исключения `.step` (обновлённые
попытки или новая капча) и `.flow` (тот же поток, готовый к следующей попытке;
`None`, если продолжить нельзя). Истёкший поток — `FlowExpired`, неизвестный
шаг Госуслуг — `UnsupportedStep`. `repr` потока не содержит секретов.

## Student: методы

`api.student(token)` не ходит в сеть; контекст ученика (его идентификаторы)
запрашивается лениво и один раз на экземпляр даже при множестве параллельных
вызовов. `student.token` — `Token`.

Периоды `start`/`end` — включительно; `start` позже `end` или слишком длинный
период — `BadRequest`.

### Чтение

| Метод | Возвращает | По умолчанию |
| --- | --- | --- |
| `me()` | `Me` | |
| `avatar()` | `Avatar` | нет аватарки — `NoAvatar` |
| `school()` | `School` | |
| `marks(start=None, end=None)` | `list[Mark]` | с начала учебного года по сегодня, до 366 дней; задан только `end` в прошлом — с начала учебного года этой даты |
| `mark(mark_id)` | `MarkDetail` | |
| `final_marks(year=None)` | `list[FinalMark]` | текущий учебный год |
| `subjects()` | `list[SubjectSummary]` | |
| `subject(subject_id)` | `SubjectDetail` | |
| `rating(on=None, subject=None)` | `Rating` | `on` — сегодня |
| `rating_subjects(on=None)` | `list[SubjectRating]` | сегодня |
| `rating_history(start=None, end=None)` | `list[RatingPoint]` | с начала учебного года по сегодня; только `end` — с начала учебного года этой даты |
| `schedule(start=None, end=None)` | `list[ScheduleItem]` | текущая неделя, до 31 дня; дали одну границу — недостающая через 6 дней |
| `lesson(lesson_id)` | `Lesson` | |
| `homework(start=None, end=None)` | `list[Homework]` | от сегодня на неделю вперёд, до 31 дня |
| `exams()` | `list[Exam]` | |
| `settings()` | `Settings` | |
| `identity()` | `Identity` | карточка ученика закрыта (403) или её нет (404) — поля карточки `null`; таймаут, сеть, 5xx и непонятный ответ — ошибка, а не пустая карточка |
| `notifications()` | `list[Notification]` | |
| `periods(start=None, end=None)` | `list[PeriodDay]` | весь текущий учебный год, до 366 дней; задан один край — учебный год этого края |
| `curriculum()` | `Curriculum` | |
| `work_program(group_id)` | `list[ProgramModule]` | рабочая программа группы (разделы, темы, уроки с датами); группы — `identity().person.groups` |
| `subject_topics(subject_id)` | `list[SubjectTopic]` | темы предмета и ожидаемые результаты |
| `control_works(start=None, end=None)` | `list[ControlWork]` | весь учебный год, до 366 дней. Форма ответа живьём не подтверждена (ответы были пустыми) |
| `final_marks_file(year=None, orientation="portrait")` | `DiaryFile` | PDF итоговых оценок за учебный год (текущий); `orientation` — `portrait` или `landscape` |
| `certificates()` | `list[Certificate]` | заявки на справки за два года; только через родителя, ученику — `NotForRole`. Форма ответа живьём не подтверждена (списки были пустыми) |
| `school_teachers(name=None)` | `list[SchoolTeacher]` | все учителя школы; `name` — поиск по части имени |
| `academic_debts(year=None)` | `list[AcademicDebt]` | текущий учебный год; только долги этого ученика. Форма ответа живьём не подтверждена (ответы были пустыми) |

Ответ дневника другой формы (например, `null` вместо списка) —
`UpstreamFormat`; в сообщении только пути полей, без значений.

### Запись

| Метод | Что делает | Права ключа (сервис) |
| --- | --- | --- |
| `homework_done(homework_id)` | отметить задание выполненным | любой ключ |
| `homework_undone(homework_id)` | снять отметку | любой ключ |
| `update_settings(update)` | `SettingsUpdate`: меняет настройки приложения | любой ключ |
| `update_contact(contact_id, value)` | меняет адрес почты контакта; значение не адрес (3-255 символов, одна `@`, без пробелов) — `BadRequest` до обращения к дневнику, и в ядре, и на сервере | `write_profile` |

Запись не повторяется автоматически. Если исход неизвестен (сеть, таймаут,
502/504 дневника, дедлайн вызова) — `WriteUncertain`: перечитайте состояние.
У исключения `.cause` — причина (`UpstreamError`/`UpstreamTimeout`), `.code` и
HTTP-статус повторяют причину, `.upstream_status` — статус дневника, если он
известен (401/403 значит, что запись точно не прошла). Определённый отказ
дневника на записи (400, 401, 403, 500) — обычная ошибка, не `WriteUncertain`;
так же ведёт себя и `RemoteDiary`.

`SettingsUpdate` меняет только то, что в дневнике уже есть: нет группы настроек
— `SettingsMissing`, поля нет — `SettingNotSet`, текущее значение вне
допустимых — `SettingUnrestorable`. Поля: `goal` (bool), `theme`
(`SettingsThemeUpdate`: `type` `dark|light`, `is_automatic`, `color_pattern`
`indigo|violet|pink`), `schedule_type` (`compact|full`). Хотя бы одно поле;
`null` не принимается. `estimation_type` не пишется.

`update_contact` правит только почту; для другого контакта —
`UnsupportedContact`.

## Parent: родитель

`diary.parent(token)` — родитель, владелец токена. Объект `Parent` запросов
не делает; токен не родителя — `NotForRole` при первом вызове.

| Метод | Что |
|---|---|
| `children()` | `list[Child]`: ученики родителя (`id`, ФИО, школа, класс) |
| `student(child_id)` | `Student` выбранного ученика, все методы выше; неверный id — `NotFound` |
| `me()` | `ParentMe`: ФИО, тип, почта, телефон, срок токена |
| `identity()` | `Identity` карточки родителя (документы, контакты, адреса); школы и класса нет |
| `avatar()` | своя аватарка (`Avatar`) |
| `settings()`, `update_settings(update)` | настройки приложения родителя, общие для всех детей |
| `update_contact(contact_id, value)` | почта в карточке родителя |
| `journal_acks(child_id, start=None, end=None)` | `list[JournalAck]`: отметки «ознакомлен с дневником» по неделям; по умолчанию текущая, период ≤ 31 дня |
| `acknowledge_journal(child_id, week=None)` | отметить неделю (любой её день, по умолчанию текущая); уже отмечена — ничего не делает. Отметку видят учителя, отменить её нельзя |

Через родителя `exams()`, `avatar()`, `homework_done()` и `homework_undone()`
ученика — `NotForRole`: дневник даёт их только самому ученику. `update_settings` и `update_contact` родителя живьём не
проверены.

## Token

`Token(value, expires_at=None, method="jwt")`:

| Член | Что это |
| --- | --- |
| `value` | сам JWT; единственный способ его получить — явно |
| `expires_at` | `datetime` (UTC) или **`None`**, если срок неизвестен: токен не JWT или в нём нет `exp` (исключения не бросается) |
| `method` | `"jwt"` (готовая строка), `"password"` или `"esia"` |
| `expires_in(now=None)` | `timedelta` до срока или `None` |
| `subject_id` | `sub` из payload строкой или `None` |
| `roles` | роли из payload (`rol` строкой через запятую или списком, либо `roles`) — список строк, пустой, если нет |
| `ensure_usable(now=None)` | `TokenInvalid`, если срока нет (не токен дневника), `TokenExpired`, если он вышел; дневник не спрашивается |
| `is_expiring(within=5 минут)` | осталось не больше `within` или уже истёк; срок неизвестен — `False` |

`repr`/`str` показывают метод, срок и 6 символов SHA-256, но не значение.
Сравнение `==` идёт за постоянное время. Срок без часового пояса считается
UTC. Подпись SDK не проверяет — её проверяет дневник.

## Удалённый клиент (`diarysdk.remote`)

`RemoteDiary(base_url, api_key, *, timeout=30.0, max_rate_wait=2.0, on_token_expired=None, http=None)`
реализует тот же `DiaryLike`: `login`, `student(token)`, `aclose()`,
`async with`. Классы `RemoteLogin`, `RemoteLoginFlow`, `RemoteStudent`, `RemoteParent` — его
части, интерфейс у них тот же, что у `Login`, `LoginFlow`, `Student`.

| Параметр | Что значит |
| --- | --- |
| `base_url`, `api_key` | адрес сервиса и ключ потребителя (`X-Api-Key`) |
| `timeout` | секунд на запрос к сервису |
| `max_rate_wait` | если сервис ответил 429 с `Retry-After` не больше этого, клиент один раз подождёт и повторит; иначе `RateLimited` |
| `on_token_expired` | функция или async-функция с `Token`: зовётся один раз на каждый отказ `token_expired` |
| `http` | свой `httpx.AsyncClient`: его cookie-jar отключается, закрывать его — вам |

Чтение при обрыве сети или 502/503/504 повторяется один раз; запись — никогда
(только после 429 с коротким `Retry-After`: сервис отказал до обработки).

Отличия от ядра, которые видит вызывающий:

- ошибки сети — `NetworkError` (наследует `RemoteError`): до сервиса не дошли
  или не дождались ответа; запись при обрыве — `WriteUncertain`;
- ответ сервиса не по контракту — `RemoteError`; ключ не принят — `BadApiKey`,
  ключу не хватает разрешения — `ForbiddenScope`;
- `renew_captcha` и `close` у потока работают так же, как у ядра.

## Синхронные обёртки (`diarysdk.sync`)

`diarysdk.sync.Diary` и `diarysdk.sync.RemoteDiary` принимают те же
параметры, что async-классы, и дают те же методы без `async`/`await`. Используйте
как `with RemoteDiary(...) as api` или закрывайте `api.close()`.

- Каждый экземпляр запускает поток с циклом событий (`diarysdk-sync`);
  `close()` останавливает его. Финализатора нет: поток — демон, и незакрытый
  экземпляр живёт (вместе с соединениями) до конца процесса.
- Вызов **блокирует вызывающий поток**. Если его сделать из работающего цикла
  событий (async-функция, Jupyter), блокируется и этот цикл на время вызова:
  в async-коде пользуйтесь async-классами.
- Исключения доходят без изменений; вызов из хука `on_token_expired` внутри
  портала — `RuntimeError`.
- Типы лежат в `diarysdk/sync.pyi`: IDE и mypy видят настоящие сигнатуры.

## Протоколы

`DiaryLike`, `LoginLike`, `LoginFlowLike`, `StudentLike`, `ParentLike` — `typing.Protocol`,
которым отвечают и ядро, и удалённый клиент. Пишите код против протокола, и
он работает с обоими:

```python
from diarysdk import DiaryLike


async def school_name(api: DiaryLike, token: str) -> str | None:
    return (await api.student(token).school()).name
```

## Модели

Модели — `pydantic`-схемы, неизменяемость и строгость не навязываются:
неизвестные поля дневника отбрасываются, отсутствующие — `None`. Ниже поля
по модулям `diarysdk.models.*`.

- **auth**: `TokenResponse(token, expires_at, method)`,
  `TokenInfo(expires_at, expires_in, subject_id, roles)`,
  `LoginMfa(kind, contact, ttl, attempts_left)`,
  `LoginCaptcha(kind, image_base64, image_type, question)`,
  `Captcha(kind, image, image_type, question)`,
  `LoginStep(flow_id, step, expires_at, mfa, captcha)`.
- **common**: `Subject(id, name)`, `PersonName(last_name, first_name, middle_name)`,
  `SchoolBrief`, `ClassUnit(id, name, level)`, `Material`.
- **me**: `Me(person, school, class_, study_profile, sections, enrolled_on, token)`,
  `MePerson`, `Section`, `TokenExpiry`.
- **school**: `School(name, type, principal, address, phone, email, website,
  classroom_teachers, teachers, branches, id, county, district)`, `Teacher`, `Branch`.
- **marks**: `Mark(id, date, subject, value, scale, five, hundred, ten, weight,
  control_form, comment, is_exam, ...)`, `MarkDetail`, `FinalMark(subject,
  year_mark, attestation_mark, training_camp_mark)`, `MarkLesson`,
  `MarkDistribution`, `ClassResults`.
- **subjects**: `SubjectSummary`, `SubjectDetail`, `SubjectDetailPeriod`,
  `Period`, `Target`, `TargetPath`.
- **rating**: `Rating(enabled, date, total, class_average_five, me, class_)`,
  `RatingMe`, `RatingEntry`, `SubjectRating`, `RatingPoint(date, place)`.
- **schedule**: `ScheduleItem(id, date, start, end, subject, room, lesson_type,
  is_cancelled, marks, homework, ...)`, `HomeworkBrief`, `HomeworkCounts`.
- **lessons**: `Lesson`, `LessonTeacher`, `Theme`.
- **homework**: `Homework(id, due, assigned_on, subject, text, materials,
  attachments, is_done, ...)`, `Attachment(name, url)`. `id` — строго
  `homework_entry_student_id`, именно его принимают `homework_done`/`homework_undone`;
  если дневник его не дал, `id` — `None` (`entry_id` и `homework_id` — другие
  пространства id и для отметки не годятся).
- **exams**: `Exam(kind, subject, date, score, mark)`.
- **settings**: `Settings(goal, theme, schedule_type, estimation_type)`,
  `SettingsTheme`, `SettingsUpdate`, `SettingsThemeUpdate`.
- **identity**: `Identity(person, school, class_, representatives)`,
  `IdentityPerson`, `IdentityBase`, `Contact`, `ContactUpdate(value)`,
  `Document`, `Address`, `Education`, `EducationClass`, `Representative`
  и вспомогательные.
- **notifications**: `Notification(at, event_type, subject_name, teacher_name,
  lesson_date, mark, homework)`, `NotificationMark`, `NotificationHomework`.
- **periods**: `PeriodDay(date, type, title, description, events)`.
- **curriculum**: `Curriculum`, `CurriculumSection`, `CurriculumSubject`,
  `CurriculumSubjectWeek`, `CurriculumWeek`.

Поле `class_` — это «class» (зарезервированное слово); в JSON сервиса оно
называется `class`. Точный набор полей — в `/openapi.json` сервиса и в
исходниках моделей.

## Исключения

База — `DiaryError(message, *, status=None, retry_after=None)`. У каждого
исключения: `message` (= `str(error)`), `code` (машинный код), `status` (HTTP-статус
ответа сервиса, если был), `retry_after` (секунды) и `raw_code` (код как
прислал сервис).

Из тела ответа сервиса код `error` превращается в класс. Неизвестный код (ответ
прокси, новый код более нового сервера) разбирается по статусу: 401 —
`AuthError`, 403 — `RemoteError`, 404 — `NotFound`, 429 — `RateLimited`, 5xx —
`UpstreamError`, остальное — `DiaryError`.

| Код (`error`) | Класс | HTTP | Смысл |
| --- | --- | --- | --- |
| `diary_error` | `DiaryError` | 502 | дневник ответил ошибкой |
| `auth_error` | `AuthError` | 401 | токен или вход не приняты |
| `token_invalid` | `TokenInvalid` | 401 | дневник не принял токен (не JWT, нет заголовка) |
| `token_missing` | `TokenInvalid` | 401 | нет заголовка `Authorization` (код сервера) |
| `token_expired` | `TokenExpired` | 401 | срок токена вышел |
| `bad_credentials` | `BadCredentials` | 401 | неверный логин или пароль |
| `bad_code` | `BadCode` | 401 | неверный код входа; в теле — новый `step` |
| `bad_captcha` | `BadCaptcha` | 401 | неверная капча; в теле — новый `step` |
| `flow_expired` | `FlowExpired` | 404 | вход не найден или истёк |
| `login_blocked` | `LoginBlocked` | 409 | Госуслуги заблокировали вход |
| `unsupported_step` | `UnsupportedStep` | 422 | шаг Госуслуг, которого нет в SDK |
| `bad_request` | `BadRequest` | 400 | неверные параметры запроса |
| `not_found` | `NotFound` | 404 | в дневнике такого нет |
| `no_avatar` | `NoAvatar` | 404 | у ученика нет аватарки |
| `multiple_children` | `MultipleChildren` | 422 | токен родителя с несколькими детьми: нужен `diary.parent` |
| `not_for_role` | `NotForRole` | 422 | для этой роли дневник эти данные не отдаёт |
| `setting_error` | `SettingError` | 409 | настройку записать нельзя |
| `settings_missing` | `SettingsMissing` | 409 | в дневнике нет настроек приложения |
| `setting_unset` | `SettingNotSet` | 409 | у настройки нет значения |
| `setting_unrestorable` | `SettingUnrestorable` | 409 | текущее значение не вернуть |
| `contact_not_email` | `UnsupportedContact` | 422 | контакт не адрес почты |
| `rate_limited` | `RateLimited` | 429 | лимит запросов; `Retry-After` |
| `upstream_error` | `UpstreamError` | 502 | дневник недоступен; в теле `upstream_status` |
| `upstream_timeout` | `UpstreamTimeout` | 504 | дневник не ответил вовремя |
| `upstream_format` | `UpstreamFormat` | 502 | ответ дневника не разобрался; `problems` — пути полей |
| `remote_error` | `RemoteError` | 502 | сервис ответил не по контракту (клиент) |
| `bad_api_key` | `BadApiKey` | 403 | ключ не принят |
| `forbidden_scope` | `ForbiddenScope` | 403 | у ключа нет нужного разрешения |

Классы без своего кода в ответе:

- `NetworkError(RemoteError)` — только у `RemoteDiary`: до сервиса не дошли;
- `WriteUncertain(DiaryError)` — запись, исход которой неизвестен (см. выше); в
  HTTP отдаётся как причина (`cause`) с полем `"uncertain": true` в теле; на
  стороне клиента строится из обрыва, из ответа 502/504 с `uncertain: true` или
  из 502/504 не от сервиса (прокси: тело не JSON сервиса).

Иерархия: `DiaryError` → `AuthError` (`TokenInvalid`, `TokenExpired`,
`BadCredentials`, `BadCode`, `BadCaptcha`, `FlowExpired`, `LoginBlocked`,
`UnsupportedStep`); `BadRequest`; `NotFound` (`NoAvatar`); `MultipleChildren`;
`SettingError` (`SettingsMissing`, `SettingNotSet`, `SettingUnrestorable`);
`UnsupportedContact`; `RateLimited`; `UpstreamError` (`UpstreamTimeout`,
`UpstreamFormat`); `WriteUncertain`; `RemoteError` (`BadApiKey`,
`ForbiddenScope`, `NetworkError`).

Ни пароли, ни коды, ни ответы капчи, ни токены не попадают в `repr` и `str`
исключений.

## Сервер: запуск и настройки

```sh
pip install "diarysdk[server] @ git+https://github.com/Kriolt/DiarySDK@v0.1.0"
DIARYSDK_KEYS_FILE=./api-keys python -m diarysdk.server
```

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

Нераспознанное число — ошибка старта (`ConfigError`).

### Ключи потребителей

Файл: одна строка на ключ, `<имя> <sha256-хеш ключа> [разрешения]`;
пустые строки и `#` пропускаются, строка не по формату пропускается с
предупреждением в журнале (без её содержимого). Файл перечитывается при
изменении (проверка не чаще раза в 10 секунд). Сам ключ сервис не хранит.

Выпуск ключа:

```sh
python -m diarysdk.server.keys new <имя> [--scope login] [--scope write_profile] [--scope acknowledge_journal]
```

Ключ печатается в stderr один раз, строка для файла — в stdout. Разрешения:

| Разрешение | Что открывает |
| --- | --- |
| `login` | `/v1/auth/*`: вход по паролю и через Госуслуги |
| `write_profile` | `PUT /v1/identity/contacts/{id}`, `PUT /v1/parent/identity/contacts/{id}` |
| `acknowledge_journal` | `POST /v1/parent/journal-acks` |

Имя потребителя — латиница, цифры, `_.-`; по нему считаются лимиты и пишется
журнал.

### Лимиты и журнал

- Общий лимит: ведро жетонов на потребителя (`RATE_PER_SECOND`, `RATE_BURST`);
  превышение — `429 rate_limited` с `Retry-After`.
- Старты входа (`POST /v1/auth/password`, `POST /v1/auth/esia`): отдельно,
  5 в минуту на потребителя.
- Одновременных входов через Госуслуги ограниченное число;
  при исчерпании — `429` (3 одновременных входа на потребителя, 100 всего).
- Журнал — JSON-строки в stdout: метод, путь, статус, время, число запросов к
  дневнику. Заголовки, тела, токены и значения параметров не пишутся.

### Docker

Образ собирается из `Dockerfile` в корне: Python 3.15, пользователь uid 10001,
`DIARYSDK_HOST=0.0.0.0`, файл ключей — `DIARYSDK_KEYS_FILE`
(`/etc/diarysdk/api-keys`; монтируйте его только для чтения), встроенная
проверка здоровья по `/healthz`, работает с `--read-only`.

```sh
docker build -t diarysdk .
docker run --rm -p 8000:8000 --read-only \
  -v "$PWD/api-keys:/etc/diarysdk/api-keys:ro" diarysdk
```

## HTTP-контракт

Базовый путь `/v1`. Заголовки:

- `X-Api-Key: <ключ>` — всегда (кроме `/healthz`);
- `Authorization: Bearer <токен ученика>` — на всех маршрутах, кроме `/v1/auth/*`
  (кроме `GET /v1/auth/token`).

`403` всегда про ключ (`bad_api_key`, `forbidden_scope`), `401` — про токен или
вход пользователя. Тело ошибки: `{"error": <код>, "message": <текст>}`; у
`bad_code`/`bad_captcha` добавляется `step`, у `upstream_error` —
`upstream_status`; у записи с неизвестным исходом (502/504) —
`"uncertain": true` (поле добавлено в 0.1.0 и необязательное: нет поля — запись
точно не прошла); у `429` — заголовок `Retry-After`. Ошибки разбора параметров —
`400 bad_request` (значения параметров в сообщении не приводятся).

Служебное: `GET /healthz` → `200 {"status":"ok"}` с `X-App-Version` (без ключа),
`GET /openapi.json` — схема (то же в `/docs`).

### Вход

| Метод и путь | Тело | Успех | Ошибки |
| --- | --- | --- | --- |
| `POST /v1/auth/password` | `{login, password}` | `200 {token, expires_at, method}` | 400, 401 `bad_credentials`, 403, 409 `login_blocked`, 422, 429, 502, 504 |
| `POST /v1/auth/esia` | `{login, password}` | `200` токен или `202` шаг входа | то же |
| `POST /v1/auth/esia/{flow_id}/code` | `{code}` (4–8 цифр) | `200` токен или `202` шаг | 401 `bad_code`, 404 `flow_expired`, 409, 422, 429, 502, 504 |
| `POST /v1/auth/esia/{flow_id}/captcha` | `{answer}` | `200` токен или `202` шаг | 401 `bad_captcha`, 404, 409, 422, 429, 502, 504 |
| `POST /v1/auth/esia/{flow_id}/captcha/renew` | — | `202` шаг со свежей капчей | 404, 422, 429, 502, 504 |
| `DELETE /v1/auth/esia/{flow_id}` | — | `204` | 400, 403, 409, 429 |
| `GET /v1/auth/token` | `Authorization` | `200 {expires_at, expires_in, subject_id, roles}` | 401, 403, 429 |

Шаг входа (`202`): `{flow_id, step: "mfa"|"captcha", expires_at, mfa?, captcha?}`.
Все маршруты `/v1/auth/*`, кроме `GET /v1/auth/token`, требуют разрешения
`login`.

### Данные ученика (`Authorization` обязателен)

Для чтения возможны `200` и ошибки 400 (для маршрутов с параметрами), 401, 403,
422 (`multiple_children`), 429, 502, 504; для записи `204` и те же ошибки плюс
404, 409.

| Метод и путь | Параметры | Ответ |
| --- | --- | --- |
| `GET /v1/me` | | `Me` |
| `GET /v1/me/avatar` | | байты картинки (`404 no_avatar`) |
| `GET /v1/school` | | `School` |
| `GET /v1/marks` | `from`, `to` | `list[Mark]` |
| `GET /v1/marks/{mark_id}` | | `MarkDetail` (404) |
| `GET /v1/final-marks` | `year` | `list[FinalMark]` |
| `GET /v1/subjects` | | `list[SubjectSummary]` |
| `GET /v1/subjects/{subject_id}` | | `SubjectDetail` (404) |
| `GET /v1/rating` | `date`, `subject` | `Rating` |
| `GET /v1/rating/subjects` | `date` | `list[SubjectRating]` |
| `GET /v1/rating/history` | `from`, `to` | `list[RatingPoint]` |
| `GET /v1/schedule` | `from`, `to` | `list[ScheduleItem]` |
| `GET /v1/lessons/{lesson_id}` | | `Lesson` (404) |
| `GET /v1/homework` | `from`, `to` | `list[Homework]` |
| `POST /v1/homework/{homework_id}/done` | | `204` (404) |
| `DELETE /v1/homework/{homework_id}/done` | | `204` (404) |
| `GET /v1/exams` | | `list[Exam]` |
| `GET /v1/settings` | | `Settings` |
| `PATCH /v1/settings` | тело `SettingsUpdate` | `204` (409 `settings_missing`, `setting_unset`, `setting_unrestorable`) |
| `GET /v1/identity` | | `Identity` |
| `PUT /v1/identity/contacts/{contact_id}` | тело `{value}`; разрешение `write_profile` | `204` (404, 422 `contact_not_email`) |
| `GET /v1/notifications` | | `list[Notification]` |
| `GET /v1/periods` | `from`, `to` | `list[PeriodDay]` |
| `GET /v1/curriculum` | | `Curriculum` |
| `GET /v1/school/teachers` | `name` | `list[SchoolTeacher]` |
| `GET /v1/final-marks/file` | `year`, `orientation` | PDF (`application/pdf`, имя файла в `Content-Disposition`) |
| `GET /v1/certificates` | `child_id` (токен родителя) | `list[Certificate]` |
| `GET /v1/groups/{group_id}/program` | | `list[ProgramModule]` |
| `GET /v1/subjects/{subject_id}/topics` | | `list[SubjectTopic]` |
| `GET /v1/control-works` | `from`, `to` | `list[ControlWork]` |
| `GET /v1/academic-debts` | `year` | `list[AcademicDebt]` |

Даты — `YYYY-MM-DD`. На записи `502`/`504` с `"uncertain": true` (или без
JSON сервиса, как у прокси) значат, что исход неизвестен (`WriteUncertain` у
клиента); `502`/`504` без этой метки — определённый отказ дневника.
