# 2. Чтение данных

[Документация](../index.md) » [Учебник](index.md) » 2. Чтение данных

## 2.1. Методы ученика

У [`Student`](../library/diarysdk.md#diarysdk.Student) по методу на раздел
дневника:

| Что | Метод |
| --- | --- |
| профиль, карточка, аватарка | `me()`, `identity()`, `avatar()` |
| школа и учителя | `school()`, `school_teachers()` |
| оценки | `marks()`, `mark(id)`, `final_marks()`, `final_marks_file()`, `academic_debts()` |
| предметы | `subjects()`, `subject(id)`, `subject_topics(id)`, `control_works()` |
| рейтинг | `rating()`, `rating_subjects()`, `rating_history()` |
| расписание | `schedule()`, `lesson(id)`, `periods()`, `curriculum()`, `work_program(id)` |
| домашние задания | `homework()` |
| прочее | `exams()`, `certificates()`, `notifications()`, `settings()` |

Методы, которые что-то меняют, — в [главе 5](5-writing.md).

## 2.2. Периоды и даты

Методы со списками за время — `marks()`, `homework()`, `schedule()` и
другие — принимают `start` и `end` типа `datetime.date`. Границы входят в
период. Без них берётся разумный период по умолчанию: для оценок — с начала
учебного года по сегодня, для ДЗ — неделя вперёд, для расписания — текущая
неделя. Точные правила — у каждого метода в
[справочнике](../library/diarysdk.md#diarysdk.Student).

<!-- test -->
```python
import asyncio
import os
from datetime import date

from diarysdk import Diary


async def main() -> None:
    async with Diary() as api:
        student = api.student(os.environ["DIARY_TOKEN"])
        autumn = await student.marks(start=date(2026, 9, 1), end=date(2026, 10, 31))
        for mark in autumn:
            print(mark.date, mark.subject.name, mark.value)


asyncio.run(main())
```

Все даты — по Москве: «сегодня» для SDK наступает в полночь по московскому
времени, где бы ни работал ваш код. Время (`datetime`) всегда с часовым
поясом.

Слишком длинный период или начало позже конца —
[`BadRequest`](../library/errors.md#diarysdk.errors.BadRequest) ещё до
запроса к дневнику.

## 2.3. Модели

Методы возвращают модели из [`diarysdk.models`](../library/models.md) —
схемы pydantic. С ними работают как с обычными объектами, а в JSON
превращают через `model_dump`:

<!-- test -->
```python
import asyncio
import json
import os

from diarysdk import Diary


async def main() -> None:
    async with Diary() as api:
        student = api.student(os.environ["DIARY_TOKEN"])
        marks = await student.marks()
        rows = [mark.model_dump(mode="json") for mark in marks]
        print(json.dumps(rows, ensure_ascii=False)[:80])


asyncio.run(main())
```

Помните три правила:

- **почти любое поле может быть `None`**: дневник часто не заполняет поля, и
  SDK не придумывает значения. Списки при этом пустые, а не `None`;
- **оценка — строка**: `mark.value` бывает `"9"`, а бывает `"зч"`; числовые
  пересчёты дневника — в `five`, `ten`, `hundred`;
- **`class_`** — поле с классом ученика; в JSON оно называется `class`.

## 2.4. Несколько запросов сразу

Ядро асинхронное, поэтому независимые запросы можно отправить одновременно.
Контекст ученика при этом запрашивается один раз:

<!-- test -->
```python
import asyncio
import os

from diarysdk import Diary


async def main() -> None:
    async with Diary() as api:
        student = api.student(os.environ["DIARY_TOKEN"])
        school, marks, homework = await asyncio.gather(
            student.school(), student.marks(), student.homework()
        )
        print(school.name, len(marks), "оценок,", len(homework), "заданий")


asyncio.run(main())
```

Дальше — [вход и токены](3-login.md).
