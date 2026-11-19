# HTTP API сервиса

[Документация](index.md) » HTTP API

---

Контракт [сервиса DiarySDK](library/server.md) для тех, кто ходит в него не
через [`RemoteDiary`](library/remote.md#diarysdk.remote.RemoteDiary), а
напрямую — из другого языка или через `curl`. Машиночитаемая схема — у
самого сервиса: `GET /openapi.json` (интерактивно — `/docs`).

## Общие правила

**Базовый путь** — `/v1`. Даты — `YYYY-MM-DD`, время — ISO 8601 с часовым
поясом. Тела запросов и ответов — JSON; модели ответов описаны в
[`diarysdk.models`](library/models.md), поле `class_` в JSON называется
`class`.

**Заголовки:**

- `X-Api-Key: <ключ>` — всегда, кроме `/healthz`;
- `Authorization: Bearer <токен>` — на всех маршрутах, кроме `/v1/auth/*`
  (но `GET /v1/auth/token` его требует).

```sh
curl -H "X-Api-Key: $DIARYSDK_KEY" -H "Authorization: Bearer $DIARY_TOKEN" \
  "https://diarysdk.example/v1/marks?from=2026-09-01&to=2026-11-19"
```

**Статусы:** `403` — всегда про ключ (`bad_api_key`, `forbidden_scope`),
`401` — про токен или вход пользователя.

**Тело ошибки:**

```json
{"error": "token_expired", "message": "Срок токена истёк, нужен новый"}
```

Дополнительные поля: у `bad_code` и `bad_captcha` — `step` (новый шаг входа),
у `upstream_error` — `upstream_status`, у записи с неизвестным исходом —
`"uncertain": true`. У `429` есть заголовок `Retry-After` (секунды). Ошибки
разбора параметров — `400 bad_request`; значения параметров в сообщение не
попадают. Все коды — в [таблице кодов](library/errors.md#коды-ошибок-сервиса).

**Запись с неизвестным исходом.** Ответ `502` или `504` на запись с
`"uncertain": true` (или вовсе не JSON сервиса, как у прокси) значит, что
исход неизвестен: перечитайте состояние. `502`/`504` без этой метки —
определённый отказ дневника, запись не прошла. Поле `uncertain` добавлено в
0.1.0 и необязательное.

**Ученик родителя.** Маршруты ученика принимают необязательный параметр
`child_id` — id из `GET /v1/parent/children`. С токеном родителя без
`child_id` выбирается единственный ребёнок; если детей несколько —
`422 multiple_children`.

## Служебное

| Метод и путь | Ответ |
| --- | --- |
| `GET /healthz` | `200 {"status": "ok"}`, заголовок `X-App-Version`; ключ не нужен |
| `GET /openapi.json` | схема API |
| `GET /docs` | та же схема, интерактивно |

## Вход

Все маршруты, кроме `GET /v1/auth/token`, требуют у ключа разрешения `login`.

| Метод и путь | Тело | Успех | Ошибки |
| --- | --- | --- | --- |
| `POST /v1/auth/password` | `{login, password}` | `200` [`TokenResponse`](library/models.md#diarysdk.models.TokenResponse) | 400, 401 `bad_credentials`, 403, 409 `login_blocked`, 422, 429, 502, 504 |
| `POST /v1/auth/esia` | `{login, password}` | `200` токен или `202` [`LoginStep`](library/models.md#diarysdk.models.LoginStep) | то же |
| `POST /v1/auth/esia/{flow_id}/code` | `{code}` (4–8 цифр) | `200` токен или `202` шаг | 401 `bad_code`, 404 `flow_expired`, 409, 422, 429, 502, 504 |
| `POST /v1/auth/esia/{flow_id}/captcha` | `{answer}` | `200` токен или `202` шаг | 401 `bad_captcha`, 404, 422, 429, 502, 504 |
| `POST /v1/auth/esia/{flow_id}/captcha/renew` | — | `202` шаг со свежей капчей | 404, 422, 429, 502, 504 |
| `DELETE /v1/auth/esia/{flow_id}` | — | `204` (и если потока нет) | 400, 403, 409, 429 |
| `GET /v1/auth/token` | — (заголовок `Authorization`) | `200` [`TokenInfo`](library/models.md#diarysdk.models.TokenInfo) | 401, 403, 429 |

Шаг входа (`202`): `{flow_id, step: "mfa" | "captcha", expires_at, mfa?, captcha?}`.
Поток живёт 5 минут с последнего шага.

## Данные ученика

Чтение отвечает `200`; ошибки — 400 (у маршрутов с параметрами), 401, 403,
422 (`multiple_children`, `not_for_role`), 429, 502, 504. Запись отвечает
`204`; ошибки — те же плюс 404 и 409.

| Метод и путь | Параметры | Ответ | Метод SDK |
| --- | --- | --- | --- |
| `GET /v1/me` | | `Me` | [`me()`](library/diarysdk.md#diarysdk.Student.me) |
| `GET /v1/me/avatar` | | картинка (`404 no_avatar`) | [`avatar()`](library/diarysdk.md#diarysdk.Student.avatar) |
| `GET /v1/identity` | | `Identity` | [`identity()`](library/diarysdk.md#diarysdk.Student.identity) |
| `PUT /v1/identity/contacts/{contact_id}` | тело `{value}`; разрешение `write_profile` | `204` (404, 422 `contact_not_email`) | [`update_contact()`](library/diarysdk.md#diarysdk.Student.update_contact) |
| `GET /v1/school` | | `School` | [`school()`](library/diarysdk.md#diarysdk.Student.school) |
| `GET /v1/school/teachers` | `name` | `list[SchoolTeacher]` | [`school_teachers()`](library/diarysdk.md#diarysdk.Student.school_teachers) |
| `GET /v1/marks` | `from`, `to` | `list[Mark]` | [`marks()`](library/diarysdk.md#diarysdk.Student.marks) |
| `GET /v1/marks/{mark_id}` | | `MarkDetail` (404) | [`mark()`](library/diarysdk.md#diarysdk.Student.mark) |
| `GET /v1/final-marks` | `year` | `list[FinalMark]` | [`final_marks()`](library/diarysdk.md#diarysdk.Student.final_marks) |
| `GET /v1/final-marks/file` | `year`, `orientation` | PDF, имя файла в `Content-Disposition` | [`final_marks_file()`](library/diarysdk.md#diarysdk.Student.final_marks_file) |
| `GET /v1/academic-debts` | `year` | `list[AcademicDebt]` | [`academic_debts()`](library/diarysdk.md#diarysdk.Student.academic_debts) |
| `GET /v1/subjects` | | `list[SubjectSummary]` | [`subjects()`](library/diarysdk.md#diarysdk.Student.subjects) |
| `GET /v1/subjects/{subject_id}` | | `SubjectDetail` (404) | [`subject()`](library/diarysdk.md#diarysdk.Student.subject) |
| `GET /v1/subjects/{subject_id}/topics` | | `list[SubjectTopic]` | [`subject_topics()`](library/diarysdk.md#diarysdk.Student.subject_topics) |
| `GET /v1/control-works` | `from`, `to` | `list[ControlWork]` | [`control_works()`](library/diarysdk.md#diarysdk.Student.control_works) |
| `GET /v1/rating` | `date`, `subject` | `Rating` | [`rating()`](library/diarysdk.md#diarysdk.Student.rating) |
| `GET /v1/rating/subjects` | `date` | `list[SubjectRating]` | [`rating_subjects()`](library/diarysdk.md#diarysdk.Student.rating_subjects) |
| `GET /v1/rating/history` | `from`, `to` | `list[RatingPoint]` | [`rating_history()`](library/diarysdk.md#diarysdk.Student.rating_history) |
| `GET /v1/schedule` | `from`, `to` | `list[ScheduleItem]` | [`schedule()`](library/diarysdk.md#diarysdk.Student.schedule) |
| `GET /v1/lessons/{lesson_id}` | | `Lesson` (404) | [`lesson()`](library/diarysdk.md#diarysdk.Student.lesson) |
| `GET /v1/periods` | `from`, `to` | `list[PeriodDay]` | [`periods()`](library/diarysdk.md#diarysdk.Student.periods) |
| `GET /v1/curriculum` | | `Curriculum` (404) | [`curriculum()`](library/diarysdk.md#diarysdk.Student.curriculum) |
| `GET /v1/groups/{group_id}/program` | | `list[ProgramModule]` | [`work_program()`](library/diarysdk.md#diarysdk.Student.work_program) |
| `GET /v1/homework` | `from`, `to` | `list[Homework]` | [`homework()`](library/diarysdk.md#diarysdk.Student.homework) |
| `POST /v1/homework/{homework_id}/done` | | `204` (404) | [`homework_done()`](library/diarysdk.md#diarysdk.Student.homework_done) |
| `DELETE /v1/homework/{homework_id}/done` | | `204` (404) | [`homework_undone()`](library/diarysdk.md#diarysdk.Student.homework_undone) |
| `GET /v1/exams` | | `list[Exam]` | [`exams()`](library/diarysdk.md#diarysdk.Student.exams) |
| `GET /v1/certificates` | только с токеном родителя | `list[Certificate]` | [`certificates()`](library/diarysdk.md#diarysdk.Student.certificates) |
| `GET /v1/notifications` | | `list[Notification]` | [`notifications()`](library/diarysdk.md#diarysdk.Student.notifications) |
| `GET /v1/settings` | | `Settings` | [`settings()`](library/diarysdk.md#diarysdk.Student.settings) |
| `PATCH /v1/settings` | тело `SettingsUpdate` | `204` (409 `settings_missing`, `setting_unset`, `setting_unrestorable`) | [`update_settings()`](library/diarysdk.md#diarysdk.Student.update_settings) |

Каждый маршрут таблицы принимает и `child_id`.

## Данные родителя

Нужен токен родителя; токен не родителя — `422 not_for_role`.

*Добавлено в версии 0.2.0.*

| Метод и путь | Параметры | Ответ | Метод SDK |
| --- | --- | --- | --- |
| `GET /v1/parent/children` | | `list[Child]` | [`children()`](library/diarysdk.md#diarysdk.Parent.children) |
| `GET /v1/parent/me` | | `ParentMe` | [`me()`](library/diarysdk.md#diarysdk.Parent.me) |
| `GET /v1/parent/identity` | | `Identity` | [`identity()`](library/diarysdk.md#diarysdk.Parent.identity) |
| `PUT /v1/parent/identity/contacts/{contact_id}` | тело `{value}`; разрешение `write_profile` | `204` | [`update_contact()`](library/diarysdk.md#diarysdk.Parent.update_contact) |
| `GET /v1/parent/avatar` | | картинка (`404 no_avatar`) | [`avatar()`](library/diarysdk.md#diarysdk.Parent.avatar) |
| `GET /v1/parent/settings` | | `Settings` | [`settings()`](library/diarysdk.md#diarysdk.Parent.settings) |
| `PATCH /v1/parent/settings` | тело `SettingsUpdate` | `204` | [`update_settings()`](library/diarysdk.md#diarysdk.Parent.update_settings) |
| `GET /v1/parent/journal-acks` | `child_id` (обязателен), `from`, `to` | `list[JournalAck]` | [`journal_acks()`](library/diarysdk.md#diarysdk.Parent.journal_acks) |
| `POST /v1/parent/journal-acks` | тело `{child_id, week?}`; разрешение `acknowledge_journal` | `204`, и если неделя уже отмечена | [`acknowledge_journal()`](library/diarysdk.md#diarysdk.Parent.acknowledge_journal) |
