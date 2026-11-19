# Справочник библиотеки

[Документация](../index.md) » Справочник библиотеки

Этот раздел описывает каждое публичное имя DiarySDK: что принимает, что
возвращает, какие исключения бросает. С чего начать и как всё связано — в
[учебнике](../tutorial/index.md).

## Модули

| Модуль | Что в нём |
| --- | --- |
| [`diarysdk`](diarysdk.md) | ядро: `Diary`, `Login`, `LoginFlow`, `Student`, `Parent`, `Hosts`, протоколы; все исключения и `Token` тоже импортируются отсюда |
| [`diarysdk.token`](token.md) | `Token` — токен дневника и его срок |
| [`diarysdk.models`](models.md) | модели ответов: оценки, расписание, ДЗ, рейтинг, карточка… |
| [`diarysdk.errors`](errors.md) | иерархия исключений и таблица «код ↔ класс ↔ HTTP-статус» |
| [`diarysdk.remote`](remote.md) | `RemoteDiary` — тот же интерфейс, но запросы идут в сервис DiarySDK |
| [`diarysdk.sync`](sync.md) | синхронные обёртки `Diary` и `RemoteDiary` |
| [`diarysdk.server`](server.md) | HTTP-сервис: `python -m diarysdk.server`, выпуск ключей, настройки |

HTTP-контракт сервиса описан отдельно — в [HTTP API](../http.md).

## Что импортировать

```python
from diarysdk import Diary, Token, DiaryError  # ядро, токен, исключения
from diarysdk.models import Homework, Mark  # модели
from diarysdk.remote import RemoteDiary  # через сервис
from diarysdk.sync import Diary as SyncDiary  # без async
```

Всё, что перечислено в `diarysdk.__all__`, `diarysdk.models.__all__`,
`diarysdk.remote.__all__` и `diarysdk.sync.__all__`, — публичный API и
меняется только по правилам [SemVer](https://semver.org/lang/ru/). Модули и
имена, начинающиеся с `_`, — внутренние.
