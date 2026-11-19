# 4. Родитель

[Документация](../index.md) » [Учебник](index.md) » 4. Родитель

*Добавлено в версии 0.2.0.*

## 4.1. Дети родителя

Токен родителя открывает его собственные данные и данные всех его учеников.
Вход — [`api.parent(token)`](../library/diarysdk.md#diarysdk.Diary.parent):

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

[`parent.student(child_id)`](../library/diarysdk.md#diarysdk.Parent.student)
— тот же [`Student`](../library/diarysdk.md#diarysdk.Student), что и в
предыдущих главах, со всеми методами.

> [!TIP]
> Если у родителя один ребёнок, подойдёт и `api.student(token)`. С несколькими
> детьми он даст [`MultipleChildren`](../library/errors.md#diarysdk.errors.MultipleChildren):
> непонятно, чьи данные нужны.

## 4.2. Что доступно родителю

Кое-что дневник отдаёт только самому ученику: через родителя `exams()`,
`avatar()`, `homework_done()` и `homework_undone()` дают
[`NotForRole`](../library/errors.md#diarysdk.errors.NotForRole). Справки об
обучении (`certificates()`), наоборот, доступны только через родителя.

У самого [`Parent`](../library/diarysdk.md#diarysdk.Parent) есть:

- `me()`, `identity()`, `avatar()` — профиль, карточка и аватарка родителя;
- `settings()`, `update_settings()` — настройки приложения, общие для всех
  детей;
- `update_contact()` — почта в карточке родителя;
- `journal_acks()` и `acknowledge_journal()` — отметка «ознакомлен с
  дневником» по неделям.

> [!WARNING]
> Отметку «ознакомлен с дневником» видят учителя, и отменить её нельзя.

Дальше — [запись](5-writing.md).
