# История изменений

Формат — по [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии —
по [SemVer](https://semver.org/lang/ru/).

## 0.2.0 — 2026-11-18

Родитель и новые разделы дневника.

- `diary.parent(token)` → `Parent`: `me()`, `identity()`, `avatar()`,
  `children()`, `student(child_id)`, `settings()`, `update_settings()`,
  `update_contact()`, отметка «ознакомлен с дневником» (`journal_acks`,
  `acknowledge_journal`). То же в `RemoteDiary` (`RemoteParent`) и `sync`.
- Сервис: маршруты `/v1/parent/*`, необязательный `child_id` в маршрутах
  ученика, разрешение ключа `acknowledge_journal`.
- Новые чтения `Student`: `school_teachers`, `academic_debts`,
  `work_program`, `subject_topics`, `control_works`, `final_marks_file`
  (PDF, `DiaryFile`), `certificates` (только через родителя). Маршруты
  `/v1/school/teachers`, `/v1/academic-debts`, `/v1/groups/{id}/program`,
  `/v1/subjects/{id}/topics`, `/v1/control-works`, `/v1/final-marks/file`,
  `/v1/certificates`.
- Ошибка `NotForRole` (`not_for_role`, 422): дневник этой роли данные не даёт
  (через родителя — `exams`, `avatar`, отметка ДЗ; ученику — справки).
- `Token.roles` читает роли из `rls` настоящего JWT (было всегда `[]`).
- `final_marks` через токен родителя больше не падает с `TokenInvalid`.
- `MultipleChildren` подсказывает `diary.parent(token).student(child_id)`.
- `live_check.py --parent`; `NoAvatar` и `NotForRole` печатаются как `skip`.

## 0.1.0 — 2026-11-16

Первый выпуск.

- Ядро `diarysdk.Diary`: прямой доступ к дневнику «Моя школа» по токену
  ученика (async): профиль, школа, оценки и итоговые оценки, предметы, рейтинг,
  расписание, уроки, домашние задания, экзамены, настройки, личные данные,
  уведомления, периоды, учебный план.
- Запись: отметка домашнего задания, настройки приложения, почта в контактах.
  Запись не повторяется автоматически; неизвестный исход — `WriteUncertain`.
- Вход: по логину и паролю и через Госуслуги (капча и код — через `LoginFlow`).
  `Token` со сроком из JWT (`expires_at` может быть `None`).
- Удалённый клиент `diarysdk.remote.RemoteDiary` с тем же интерфейсом, что у ядра,
  и ошибками `BadApiKey`, `ForbiddenScope`, `NetworkError`.
- Синхронные обёртки `diarysdk.sync` (`Diary`, `RemoteDiary`) и заглушка типов.
- Сервис `python -m diarysdk.server` (FastAPI, ключи потребителей с
  разрешениями, лимиты, журнал без секретов), выпуск ключей
  `python -m diarysdk.server.keys`, образ Docker.
- Единая иерархия ошибок с таблицей «код ↔ класс ↔ HTTP-статус».
- Документация, примеры, проверка чистоты репозитория, CI.
- Границы пакета: ядро не импортирует `diarysdk.server` (счётчик запросов — в
  `_metrics`), тест границ охватывает весь сервер и относительные импорты, CI
  проверяет установку без extras. `Avatar` лежит в `diarysdk.models`; все
  модели доступны из `diarysdk.models`; у `Token` есть `subject_id`, `roles`,
  `ensure_usable()`.
- Ошибки записи: 3xx на записи и 502/504 с `"uncertain": true` (или не от
  сервиса) — `WriteUncertain`; определённый отказ дневника — обычная ошибка,
  и в ядре, и в `RemoteDiary`. В теле ошибки сервиса появилось необязательное
  поле `uncertain`.
- `Student.update_contact` проверяет адрес почты в ядре (`BadRequest`, как на сервисе).
- `Homework.id` — только `homework_entry_student_id` (раньше при его отсутствии
  подставлялись другие id, непригодные для отметки).
- `identity()` не прячет сбои дневника за пустой карточкой; профиль для
  `me()`/`identity()` на холодном контексте запрашивается один раз.
- Вход по логину и паролю передаёт куки цепочки переадресаций; период с одним
  краем в прошлом учебном году больше не даёт «начало позже конца».
