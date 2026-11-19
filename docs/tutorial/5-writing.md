# 5. Запись

[Документация](../index.md) » [Учебник](index.md) » 5. Запись

## 5.1. Что можно записать

Дневник в основном читают, но кое-что SDK умеет менять:

| Что | Метод |
| --- | --- |
| отметка «выполнено» у ДЗ | [`homework_done(id)`](../library/diarysdk.md#diarysdk.Student.homework_done), [`homework_undone(id)`](../library/diarysdk.md#diarysdk.Student.homework_undone) |
| настройки приложения | [`update_settings(update)`](../library/diarysdk.md#diarysdk.Student.update_settings) |
| адрес почты в карточке | [`update_contact(id, value)`](../library/diarysdk.md#diarysdk.Student.update_contact) |
| «ознакомлен с дневником» (родитель) | [`acknowledge_journal(child_id)`](../library/diarysdk.md#diarysdk.Parent.acknowledge_journal) |

Настройки передаются моделью
[`SettingsUpdate`](../library/models.md#diarysdk.models.SettingsUpdate) — в ней
только то, что нужно поменять:

```python
from diarysdk.models import SettingsThemeUpdate, SettingsUpdate

await student.update_settings(SettingsUpdate(schedule_type="compact"))
await student.update_settings(SettingsUpdate(theme=SettingsThemeUpdate(type="dark")))
```

## 5.2. Неизвестный исход: `WriteUncertain`

Представьте: запрос на запись ушёл, а ответа нет — оборвалась сеть, вышел
таймаут, дневник ответил 502. Применилась ли запись? Неизвестно. Повторить её
вслепую опасно: можно сделать дело дважды.

Поэтому SDK **никогда не повторяет запись сам**. В такой ситуации он бросает
[`WriteUncertain`](../library/errors.md#diarysdk.errors.WriteUncertain), а
решение оставляет вам: перечитайте состояние и посмотрите, что получилось.

<!-- test -->
```python
import asyncio
import os

from diarysdk import Diary, WriteUncertain


async def main() -> None:
    async with Diary() as api:
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

Определённый отказ дневника — например, 400 или 403 — это обычная ошибка, а
не `WriteUncertain`: там точно известно, что запись не прошла.

Дальше — [ошибки](6-errors.md).
