# `diarysdk` — ядро: прямой доступ к дневнику

[Документация](../index.md) » [Справочник библиотеки](index.md) » `diarysdk`

**Исходный код:** [`diarysdk/client.py`](../../diarysdk/client.py),
[`diarysdk/_protocols.py`](../../diarysdk/_protocols.py)

---

Ядро ходит в дневник само, по токену ученика или родителя. Все методы,
которые обращаются к сети, — корутины: ядро асинхронное. Синхронный вариант —
[`diarysdk.sync`](sync.md), вариант через сервис —
[`diarysdk.remote`](remote.md); методы, сигнатуры и исключения у всех трёх
одинаковые.

```python
import asyncio

from diarysdk import Diary


async def main() -> None:
    async with Diary() as api:
        student = api.student("eyJ...")
        for mark in await student.marks():
            print(mark.date, mark.subject.name, mark.value)


asyncio.run(main())
```

Из `diarysdk` импортируются все публичные имена ядра (`diarysdk.__all__`):
классы этой страницы, [`Token`](token.md), [исключения](errors.md) и модели
`Avatar`, `Captcha`, `LoginMfa`, `TokenInfo`. Остальные модели — в
[`diarysdk.models`](models.md).

<a id="diarysdk.__version__"></a>

### *атрибут* `diarysdk.__version__`

Версия пакета строкой, например `"0.2.0"`.

## Дневник

<a id="diarysdk.Diary"></a>

### *класс* `diarysdk.Diary(*, hosts=None, timeout=15.0, deadline=20.0, http=None)`

Дневник «Моя школа» напрямую. Объект держит соединения, поэтому его нужно
закрыть: используйте `async with Diary() as api` или вызовите
[`aclose()`](#diarysdk.Diary.aclose).

Параметры:

- **hosts** ([`Hosts`](#diarysdk.Hosts) | `None`) — адреса дневника и
  Госуслуг; по умолчанию — боевые.
- **timeout** (`float`) — секунд на один запрос к дневнику.
- **deadline** (`float`) — секунд на весь вызов метода целиком: контекст
  ученика, сам запрос и повтор.
- **http** (`httpx.AsyncClient` | `None`) — свой HTTP-клиент: прокси, свои
  таймауты, тесты. Его cookie-jar отключается (куки входа SDK ведёт сам: общий
  jar смешал бы сессии разных учеников), а закрывает его хозяин, не SDK.

Вызов любого метода после закрытия — `RuntimeError`.

<a id="diarysdk.Diary.login"></a>

#### *атрибут* `login`

[`Login`](#diarysdk.Login): вход по паролю портала и через Госуслуги.

<a id="diarysdk.Diary.student"></a>

#### *метод* `student(token)`

Вернуть [`Student`](#diarysdk.Student) — ученика, владельца токена, или
единственного ребёнка родителя. Запросов не делает.

- **token** (`str` | [`Token`](token.md#diarysdk.Token)) — JWT дневника.

Токен родителя с несколькими детьми даёт
[`MultipleChildren`](errors.md#diarysdk.errors.MultipleChildren) при первом
вызове метода ученика: выбирайте ребёнка через
`api.parent(token).student(child_id)`.

<a id="diarysdk.Diary.parent"></a>

#### *метод* `parent(token)`

Вернуть [`Parent`](#diarysdk.Parent) — родителя, владельца токена. Запросов не
делает; токен не родителя даёт
[`NotForRole`](errors.md#diarysdk.errors.NotForRole) при первом вызове.

- **token** (`str` | [`Token`](token.md#diarysdk.Token)) — JWT дневника
  родителя.

*Добавлено в версии 0.2.0.*

<a id="diarysdk.Diary.aclose"></a>

#### *async-метод* `aclose()`

Закрыть соединения и незаконченные входы через Госуслуги. Свой
`httpx.AsyncClient`, переданный как `http=`, остаётся открытым.

<a id="diarysdk.Hosts"></a>

### *класс* `diarysdk.Hosts(dnevnik=..., school_api=..., school=..., esia=...)`

Неизменяемый набор адресов (`dataclass(frozen=True)`). Меняют его в тестах и
за прокси.

| Атрибут | По умолчанию | Что это |
| --- | --- | --- |
| `dnevnik` | `https://authedu.mosreg.ru` | дневник |
| `school_api` | `https://authedu.mosreg.ru/api` | API школы |
| `school` | `https://myschool.mosreg.ru` | портал «Моя школа» |
| `esia` | `https://esia.gosuslugi.ru` | Госуслуги; нужны только для входа |

## Вход

<a id="diarysdk.Login"></a>

### *класс* `diarysdk.Login`

Вход: логин и пароль портала или Госуслуг. Сами его не создают — берут
[`Diary.login`](#diarysdk.Diary.login). Пароли, коды и ответы капчи нигде не
сохраняются и не попадают в `repr`, исключения и журналы.

<a id="diarysdk.Login.password"></a>

#### *async-метод* `password(login, password)`

Войти по логину и паролю портала «Моя школа» и вернуть
[`Token`](token.md#diarysdk.Token) с `method="password"` и сроком из JWT.

Исключения: [`BadCredentials`](errors.md#diarysdk.errors.BadCredentials) —
неверный логин или пароль;
[`LoginBlocked`](errors.md#diarysdk.errors.LoginBlocked) — вход временно
заблокирован.

<a id="diarysdk.Login.esia"></a>

#### *async-метод* `esia(login, password)`

Войти через Госуслуги (ЕСИА). Логин — почта, телефон или СНИЛС.

Возвращает [`Token`](token.md#diarysdk.Token) с `method="esia"`, если вход
прошёл сразу, или [`LoginFlow`](#diarysdk.LoginFlow), если Госуслуги просят код
подтверждения или капчу. Поток живёт 5 минут с последнего шага.

Исключения: [`BadCredentials`](errors.md#diarysdk.errors.BadCredentials),
[`LoginBlocked`](errors.md#diarysdk.errors.LoginBlocked),
[`UnsupportedStep`](errors.md#diarysdk.errors.UnsupportedStep) — Госуслуги
просят шаг, которого SDK не умеет.

<a id="diarysdk.LoginFlow"></a>

### *класс* `diarysdk.LoginFlow`

Вход через Госуслуги, который ждёт ответа: кода или капчи. Возвращается из
[`Login.esia()`](#diarysdk.Login.esia) и из каждого следующего шага. `repr`
потока секретов не содержит.

```python
result = await api.login.esia(login, password)
while not isinstance(result, Token):
    if result.kind == "captcha":
        result = await result.answer_captcha(ask_user(result.captcha.image))
    else:
        result = await result.submit_code(ask_user(result.mfa.kind))
```

<a id="diarysdk.LoginFlow.kind"></a>

#### *свойство* `kind`

Чего ждёт вход: `"mfa"` — кода, `"captcha"` — ответа на капчу.

<a id="diarysdk.LoginFlow.mfa"></a>

#### *свойство* `mfa`

[`LoginMfa`](models.md#diarysdk.models.LoginMfa) — куда отправлен код и
сколько попыток осталось; `None`, если ждём не код.

<a id="diarysdk.LoginFlow.captcha"></a>

#### *свойство* `captcha`

[`Captcha`](models.md#diarysdk.models.Captcha) — картинка или вопрос; `None`,
если ждём не капчу.

<a id="diarysdk.LoginFlow.expires_at"></a>

#### *свойство* `expires_at`

`datetime`: когда поток истечёт, если не сделать следующий шаг.

<a id="diarysdk.LoginFlow.submit_code"></a>

#### *async-метод* `submit_code(code)`

Отправить код подтверждения из SMS, MAX или приложения-аутентификатора.
Возвращает [`Token`](token.md#diarysdk.Token) — вход завершён — или следующий
`LoginFlow`.

Исключения: [`BadCode`](errors.md#diarysdk.errors.BadCode) — неверный код; у
исключения `flow` — тот же поток с обновлённым `mfa`, код можно отправить
снова; [`FlowExpired`](errors.md#diarysdk.errors.FlowExpired) — поток истёк
или закрыт.

<a id="diarysdk.LoginFlow.answer_captcha"></a>

#### *async-метод* `answer_captcha(answer)`

Ответить на капчу: текст с картинки или ответ на вопрос. Возвращает
[`Token`](token.md#diarysdk.Token) или следующий `LoginFlow`.

Исключения: [`BadCaptcha`](errors.md#diarysdk.errors.BadCaptcha) — неверный
ответ, у исключения `flow` — поток со свежей капчей;
[`FlowExpired`](errors.md#diarysdk.errors.FlowExpired).

<a id="diarysdk.LoginFlow.renew_captcha"></a>

#### *async-метод* `renew_captcha()`

Получить другую картинку капчи. Возвращает тот же поток с новой капчей.
Исключение: [`FlowExpired`](errors.md#diarysdk.errors.FlowExpired).

<a id="diarysdk.LoginFlow.close"></a>

#### *async-метод* `close()`

Отменить вход. Повторный вызов — не ошибка.

## Ученик

<a id="diarysdk.Student"></a>

### *класс* `diarysdk.Student`

Запросы от имени одного ученика. Сами его не создают — берут
[`Diary.student(token)`](#diarysdk.Diary.student) или
[`Parent.student(child_id)`](#diarysdk.Parent.student).

Создание объекта в сеть не ходит. Контекст ученика (его идентификаторы)
запрашивается лениво и один раз на экземпляр, даже если методы вызваны
параллельно.

**Периоды.** Параметры `start` и `end` — `datetime.date`, границы
включительно, даты по Москве. Без них берётся период по умолчанию; он описан у
каждого метода. Начало позже конца или слишком длинный период —
[`BadRequest`](errors.md#diarysdk.errors.BadRequest).

**Общие исключения.** Любой метод может бросить
[`TokenInvalid`](errors.md#diarysdk.errors.TokenInvalid) или
[`TokenExpired`](errors.md#diarysdk.errors.TokenExpired) — нужен новый токен;
[`UpstreamError`](errors.md#diarysdk.errors.UpstreamError) и его подклассы
`UpstreamTimeout`, `UpstreamFormat` — дневник недоступен или ответил непонятно;
[`RateLimited`](errors.md#diarysdk.errors.RateLimited). У удалённого клиента
к ним добавляется [`RemoteError`](errors.md#diarysdk.errors.RemoteError) с
подклассами. Ниже у методов перечислены только особые исключения.

<a id="diarysdk.Student.token"></a>

#### *свойство* `token`

[`Token`](token.md#diarysdk.Token), от имени которого идут запросы.

### Профиль и школа

<a id="diarysdk.Student.me"></a>

#### *async-метод* `me()`

Кто ученик: ФИО, GUID, школа, класс, профиль обучения, кружки, срок токена.
Возвращает [`Me`](models.md#diarysdk.models.Me).

<a id="diarysdk.Student.avatar"></a>

#### *async-метод* `avatar()`

Аватарка ученика — сама картинка. Возвращает
[`Avatar`](models.md#diarysdk.models.Avatar).

Исключения: [`NoAvatar`](errors.md#diarysdk.errors.NoAvatar) — аватарки нет;
[`NotForRole`](errors.md#diarysdk.errors.NotForRole) — через родителя:
дневник отдаёт аватарку только самому ученику.

<a id="diarysdk.Student.identity"></a>

#### *async-метод* `identity()`

Карточка ученика: ФИО, документы, контакты, адреса, законные представители.
Возвращает [`Identity`](models.md#diarysdk.models.Identity).

Если карточка закрыта (403) или её нет (404), поля карточки — `None`. Таймаут,
сбой сети, 5xx и непонятный ответ — ошибка, а не пустая карточка.

<a id="diarysdk.Student.school"></a>

#### *async-метод* `school()`

Школа: директор, адрес, классные руководители, учителя, корпуса. Возвращает
[`School`](models.md#diarysdk.models.School).

<a id="diarysdk.Student.school_teachers"></a>

#### *async-метод* `school_teachers(name=None)`

Учителя школы ученика. Возвращает
`list[`[`SchoolTeacher`](models.md#diarysdk.models.SchoolTeacher)`]`.

- **name** (`str` | `None`) — часть имени для поиска; по умолчанию — все
  учителя.

*Добавлено в версии 0.2.0.*

### Оценки и предметы

<a id="diarysdk.Student.marks"></a>

#### *async-метод* `marks(start=None, end=None)`

Оценки за период. Возвращает
`list[`[`Mark`](models.md#diarysdk.models.Mark)`]`.

По умолчанию — с 1 сентября текущего учебного года по сегодня; задан только
`end` в прошлом — с начала учебного года этой даты. Период — не длиннее 366
дней.

<a id="diarysdk.Student.mark"></a>

#### *async-метод* `mark(mark_id)`

Оценка подробно: учитель, урок, итоги класса за работу. Возвращает
[`MarkDetail`](models.md#diarysdk.models.MarkDetail).

- **mark_id** (`int`) — `Mark.id` из [`marks()`](#diarysdk.Student.marks).

Исключение: [`NotFound`](errors.md#diarysdk.errors.NotFound) — такой оценки
нет.

<a id="diarysdk.Student.final_marks"></a>

#### *async-метод* `final_marks(year=None)`

Годовые оценки за учебный год. Возвращает
`list[`[`FinalMark`](models.md#diarysdk.models.FinalMark)`]`.

- **year** (`int` | `None`) — год начала учебного года: `2025` — это 2025/26.
  По умолчанию — текущий.

Исключение: [`BadRequest`](errors.md#diarysdk.errors.BadRequest) — учебный год
ещё не начался.

<a id="diarysdk.Student.final_marks_file"></a>

#### *async-метод* `final_marks_file(year=None, orientation="portrait")`

PDF итоговых оценок за учебный год — как кнопка «Скачать» на сайте.
Возвращает [`DiaryFile`](models.md#diarysdk.models.DiaryFile): байты PDF, тип
`application/pdf` и имя файла.

- **year** (`int` | `None`) — год начала учебного года; по умолчанию — текущий.
- **orientation** (`"portrait"` | `"landscape"`) — ориентация страницы.

Исключение: [`BadRequest`](errors.md#diarysdk.errors.BadRequest) — неверная
ориентация или учебный год ещё не начался.

*Добавлено в версии 0.2.0.*

<a id="diarysdk.Student.academic_debts"></a>

#### *async-метод* `academic_debts(year=None)`

Академические задолженности ученика за учебный год. Возвращает
`list[`[`AcademicDebt`](models.md#diarysdk.models.AcademicDebt)`]`.

- **year** (`int` | `None`) — год начала учебного года; по умолчанию — текущий.

Дневник отвечает по всему классу; SDK оставляет только строки этого ученика.
Исключение: [`BadRequest`](errors.md#diarysdk.errors.BadRequest) — учебный год
ещё не начался.

> [!NOTE]
> Форма ответа живьём не подтверждена: все наблюдавшиеся ответы были пустыми.

*Добавлено в версии 0.2.0.*

<a id="diarysdk.Student.subjects"></a>

#### *async-метод* `subjects()`

Предметы со средними баллами ученика и оценками по периодам. Возвращает
`list[`[`SubjectSummary`](models.md#diarysdk.models.SubjectSummary)`]`.

<a id="diarysdk.Student.subject"></a>

#### *async-метод* `subject(subject_id)`

Предмет подробно: оценки по периодам, цели, итоги. Возвращает
[`SubjectDetail`](models.md#diarysdk.models.SubjectDetail).

- **subject_id** (`int`) — id предмета из [`subjects()`](#diarysdk.Student.subjects).

Исключение: [`NotFound`](errors.md#diarysdk.errors.NotFound) — такого
предмета нет.

<a id="diarysdk.Student.subject_topics"></a>

#### *async-метод* `subject_topics(subject_id)`

Темы предмета и ожидаемые результаты по ним. Возвращает
`list[`[`SubjectTopic`](models.md#diarysdk.models.SubjectTopic)`]`.

- **subject_id** (`int`) — id предмета из [`subjects()`](#diarysdk.Student.subjects).

*Добавлено в версии 0.2.0.*

<a id="diarysdk.Student.control_works"></a>

#### *async-метод* `control_works(start=None, end=None)`

Контрольные работы за период. Возвращает
`list[`[`ControlWork`](models.md#diarysdk.models.ControlWork)`]`.

По умолчанию — весь текущий учебный год; период — не длиннее 366 дней.

> [!NOTE]
> Форма ответа живьём не подтверждена: все наблюдавшиеся ответы были пустыми.

*Добавлено в версии 0.2.0.*

### Рейтинг

<a id="diarysdk.Student.rating"></a>

#### *async-метод* `rating(on=None, subject=None)`

Место ученика в рейтинге класса и места одноклассников. Возвращает
[`Rating`](models.md#diarysdk.models.Rating); если в школе рейтинг выключен —
`Rating(enabled=False)`, остальные поля `None`.

- **on** (`datetime.date` | `None`) — на какую дату; по умолчанию — сегодня.
- **subject** (`int` | `None`) — id предмета; по умолчанию — по всем
  предметам.

<a id="diarysdk.Student.rating_subjects"></a>

#### *async-метод* `rating_subjects(on=None)`

Место ученика в классе по каждому предмету. Возвращает
`list[`[`SubjectRating`](models.md#diarysdk.models.SubjectRating)`]`.

- **on** (`datetime.date` | `None`) — на какую дату; по умолчанию — сегодня.

<a id="diarysdk.Student.rating_history"></a>

#### *async-метод* `rating_history(start=None, end=None)`

Место в рейтинге класса по дням. Возвращает
`list[`[`RatingPoint`](models.md#diarysdk.models.RatingPoint)`]`.

По умолчанию — с начала учебного года по сегодня; задан только `end` — с
начала учебного года этой даты.

### Расписание и уроки

<a id="diarysdk.Student.schedule"></a>

#### *async-метод* `schedule(start=None, end=None)`

Уроки и события календаря с оценками и ДЗ. Возвращает
`list[`[`ScheduleItem`](models.md#diarysdk.models.ScheduleItem)`]`.

По умолчанию — текущая неделя; задана одна граница — вторая через 6 дней.
Период — не длиннее 31 дня.

<a id="diarysdk.Student.lesson"></a>

#### *async-метод* `lesson(lesson_id)`

Урок подробно: тема, учитель, оценки, ДЗ, материалы. Возвращает
[`Lesson`](models.md#diarysdk.models.Lesson).

- **lesson_id** (`int`) — `ScheduleItem.id` из [`schedule()`](#diarysdk.Student.schedule).

Исключение: [`NotFound`](errors.md#diarysdk.errors.NotFound) — такого урока
нет.

<a id="diarysdk.Student.periods"></a>

#### *async-метод* `periods(start=None, end=None)`

Учебные дни, каникулы и праздники по дням. Возвращает
`list[`[`PeriodDay`](models.md#diarysdk.models.PeriodDay)`]`.

По умолчанию — весь текущий учебный год; задан один край — учебный год этого
края. Период — не длиннее 366 дней.

<a id="diarysdk.Student.curriculum"></a>

#### *async-метод* `curriculum()`

Учебный план параллели: предметы и часы по неделям. Возвращает
[`Curriculum`](models.md#diarysdk.models.Curriculum).

Исключение: [`NotFound`](errors.md#diarysdk.errors.NotFound) — плана у ученика
нет.

<a id="diarysdk.Student.work_program"></a>

#### *async-метод* `work_program(group_id)`

Рабочая программа учебной группы: разделы, темы и уроки с датами. Возвращает
`list[`[`ProgramModule`](models.md#diarysdk.models.ProgramModule)`]`.

- **group_id** (`int`) — id группы из `identity().person.groups`
  ([`StudyGroup.id`](models.md#diarysdk.models.StudyGroup)).

*Добавлено в версии 0.2.0.*

### Домашние задания

<a id="diarysdk.Student.homework"></a>

#### *async-метод* `homework(start=None, end=None)`

Домашние задания по дате сдачи. Возвращает
`list[`[`Homework`](models.md#diarysdk.models.Homework)`]`.

По умолчанию — от сегодня на неделю вперёд; период — не длиннее 31 дня.

<a id="diarysdk.Student.homework_done"></a>

#### *async-метод* `homework_done(homework_id)`

Отметить домашнее задание выполненным.

- **homework_id** (`int`) — [`Homework.id`](models.md#diarysdk.models.Homework)
  из [`homework()`](#diarysdk.Student.homework). Если `id` равен `None`,
  дневник не дал нужный идентификатор, и отметить такое задание нельзя.

Исключения: [`WriteUncertain`](errors.md#diarysdk.errors.WriteUncertain) —
сбой сети или 502/504 во время записи; прошла ли она, неизвестно, перечитайте
`homework()`. [`NotForRole`](errors.md#diarysdk.errors.NotForRole) — через
родителя: отмечать ДЗ может только сам ученик.

<a id="diarysdk.Student.homework_undone"></a>

#### *async-метод* `homework_undone(homework_id)`

Снять отметку о выполнении. Параметр и исключения — как у
[`homework_done()`](#diarysdk.Student.homework_done).

### Экзамены, справки, уведомления

<a id="diarysdk.Student.exams"></a>

#### *async-метод* `exams()`

ОГЭ и ЕГЭ ученика, в том числе пробные. Возвращает
`list[`[`Exam`](models.md#diarysdk.models.Exam)`]`.

Исключение: [`NotForRole`](errors.md#diarysdk.errors.NotForRole) — через
родителя: экзамены дневник отдаёт только самому ученику.

<a id="diarysdk.Student.certificates"></a>

#### *async-метод* `certificates()`

Заявки на справки об обучении за последние два года. Возвращает
`list[`[`Certificate`](models.md#diarysdk.models.Certificate)`]`.

Исключение: [`NotForRole`](errors.md#diarysdk.errors.NotForRole) — токен
ученика: справки дневник отдаёт только родителю. Вызывайте через
`api.parent(token).student(child_id).certificates()`.

> [!NOTE]
> Форма ответа живьём не подтверждена: все наблюдавшиеся списки были пустыми.

*Добавлено в версии 0.2.0.*

<a id="diarysdk.Student.notifications"></a>

#### *async-метод* `notifications()`

Лента дневника: новые и изменённые оценки, ДЗ и прочее. Возвращает
`list[`[`Notification`](models.md#diarysdk.models.Notification)`]`.

### Настройки и контакты

<a id="diarysdk.Student.settings"></a>

#### *async-метод* `settings()`

Настройки приложения владельца токена. Возвращает
[`Settings`](models.md#diarysdk.models.Settings); если настройки не
задавались — все поля `None`. Через родителя это настройки самого родителя,
общие для всех детей.

<a id="diarysdk.Student.update_settings"></a>

#### *async-метод* `update_settings(update)`

Изменить настройки приложения: только переданные поля.

- **update** ([`SettingsUpdate`](models.md#diarysdk.models.SettingsUpdate)) —
  новые значения, хотя бы одно поле.

Меняются только поля, у которых в дневнике уже есть значение. Исключения:
[`SettingsMissing`](errors.md#diarysdk.errors.SettingsMissing) — группы
настроек в дневнике нет, записывать некуда;
[`SettingNotSet`](errors.md#diarysdk.errors.SettingNotSet) — у поля нет
значения; [`SettingUnrestorable`](errors.md#diarysdk.errors.SettingUnrestorable)
— текущее значение SDK записать не умеет, поэтому перезапись не вернуть;
[`WriteUncertain`](errors.md#diarysdk.errors.WriteUncertain).

```python
from diarysdk.models import SettingsThemeUpdate, SettingsUpdate

await student.update_settings(SettingsUpdate(theme=SettingsThemeUpdate(type="dark")))
```

<a id="diarysdk.Student.update_contact"></a>

#### *async-метод* `update_contact(contact_id, value)`

Заменить адрес почты в контакте ученика. Другие виды контактов не меняются.

- **contact_id** (`int`) — [`Contact.id`](models.md#diarysdk.models.Contact) из
  `identity().person.contacts`.
- **value** (`str`) — новый адрес: 3–255 символов, ровно одна `@` с непустыми
  частями, без пробелов.

Исключения: [`BadRequest`](errors.md#diarysdk.errors.BadRequest) — значение не
адрес почты (проверяется до обращения к дневнику);
[`UnsupportedContact`](errors.md#diarysdk.errors.UnsupportedContact) — контакт
не почта; [`NotFound`](errors.md#diarysdk.errors.NotFound) — такого контакта
нет; [`ForbiddenScope`](errors.md#diarysdk.errors.ForbiddenScope) — у
удалённого клиента: у ключа нет разрешения `write_profile`;
[`WriteUncertain`](errors.md#diarysdk.errors.WriteUncertain).

## Родитель

<a id="diarysdk.Parent"></a>

### *класс* `diarysdk.Parent`

Родитель — владелец токена: его собственные данные и доступные ему ученики.
Сами его не создают — берут [`Diary.parent(token)`](#diarysdk.Diary.parent).
Объект запросов не делает. Общие исключения — как у
[`Student`](#diarysdk.Student); токен не родителя —
[`NotForRole`](errors.md#diarysdk.errors.NotForRole).

```python
parent = api.parent(token)
for child in await parent.children():
    marks = await parent.student(child.id).marks()
```

*Добавлено в версии 0.2.0.*

<a id="diarysdk.Parent.token"></a>

#### *свойство* `token`

[`Token`](token.md#diarysdk.Token) родителя.

<a id="diarysdk.Parent.children"></a>

#### *async-метод* `children()`

Ученики, к которым у родителя есть доступ. Возвращает
`list[`[`Child`](models.md#diarysdk.models.Child)`]`; если детей в профиле
нет — пустой список.

<a id="diarysdk.Parent.student"></a>

#### *метод* `student(child_id)`

Вернуть [`Student`](#diarysdk.Student) выбранного ученика со всеми его
методами. Запросов не делает.

- **child_id** (`int`) — [`Child.id`](models.md#diarysdk.models.Child) из
  [`children()`](#diarysdk.Parent.children).

Неверный id — [`NotFound`](errors.md#diarysdk.errors.NotFound) при первом
вызове, `child_id <= 0` —
[`BadRequest`](errors.md#diarysdk.errors.BadRequest).

> [!NOTE]
> Кое-что дневник отдаёт только самому ученику: через родителя `exams()`,
> `avatar()`, `homework_done()` и `homework_undone()` дают
> [`NotForRole`](errors.md#diarysdk.errors.NotForRole). Справки
> (`certificates()`), наоборот, доступны только через родителя.

<a id="diarysdk.Parent.me"></a>

#### *async-метод* `me()`

Профиль родителя: ФИО, тип, почта, телефон, срок токена. Возвращает
[`ParentMe`](models.md#diarysdk.models.ParentMe).

<a id="diarysdk.Parent.identity"></a>

#### *async-метод* `identity()`

Карточка родителя: документы, контакты, адреса. Возвращает
[`Identity`](models.md#diarysdk.models.Identity); школы и класса в ней нет.

<a id="diarysdk.Parent.avatar"></a>

#### *async-метод* `avatar()`

Аватарка родителя. Возвращает [`Avatar`](models.md#diarysdk.models.Avatar).
Исключение: [`NoAvatar`](errors.md#diarysdk.errors.NoAvatar).

<a id="diarysdk.Parent.settings"></a>

#### *async-метод* `settings()`

Настройки приложения родителя, общие для всех детей. Возвращает
[`Settings`](models.md#diarysdk.models.Settings).

<a id="diarysdk.Parent.update_settings"></a>

#### *async-метод* `update_settings(update)`

Изменить настройки приложения родителя. Параметр и исключения — как у
[`Student.update_settings()`](#diarysdk.Student.update_settings).

> [!WARNING]
> Живьём не проверено.

<a id="diarysdk.Parent.update_contact"></a>

#### *async-метод* `update_contact(contact_id, value)`

Заменить адрес почты в карточке родителя. Параметры и исключения — как у
[`Student.update_contact()`](#diarysdk.Student.update_contact).

> [!WARNING]
> Живьём не проверено.

<a id="diarysdk.Parent.journal_acks"></a>

#### *async-метод* `journal_acks(child_id, start=None, end=None)`

Отметки «ознакомлен с дневником» по неделям. Возвращает
`list[`[`JournalAck`](models.md#diarysdk.models.JournalAck)`]`.

- **child_id** (`int`) — [`Child.id`](models.md#diarysdk.models.Child).
- **start, end** (`datetime.date` | `None`) — по умолчанию текущая неделя;
  начало сдвигается на понедельник; период — не длиннее 31 дня.

Исключения: [`NotFound`](errors.md#diarysdk.errors.NotFound) — такого ученика
у родителя нет; [`BadRequest`](errors.md#diarysdk.errors.BadRequest) —
`child_id <= 0`, начало позже конца или период длиннее 31 дня.

<a id="diarysdk.Parent.acknowledge_journal"></a>

#### *async-метод* `acknowledge_journal(child_id, week=None)`

Отметить «ознакомлен с дневником» за неделю.

- **child_id** (`int`) — [`Child.id`](models.md#diarysdk.models.Child).
- **week** (`datetime.date` | `None`) — любой день недели; по умолчанию —
  текущая.

Неделя уже отмечена — метод ничего не делает, в том числе при одновременных
вызовах. Исключения: [`BadRequest`](errors.md#diarysdk.errors.BadRequest) —
неделя ещё не наступила или `child_id <= 0`;
[`NotFound`](errors.md#diarysdk.errors.NotFound);
[`WriteUncertain`](errors.md#diarysdk.errors.WriteUncertain).

> [!WARNING]
> Отметку видят учителя, и отменить её нельзя.

## Протоколы

Ядро, удалённый клиент и синхронные обёртки отвечают одним и тем же
`typing.Protocol`. Пишите код против протокола — и он будет работать с любым
из них:

```python
from diarysdk import DiaryLike


async def school_name(api: DiaryLike, token: str) -> str | None:
    return (await api.student(token).school()).name
```

Тексты документации методов (`help()`, подсказки IDE) написаны один раз — в
протоколах — и общие для всех реализаций.

<a id="diarysdk.DiaryLike"></a>

### *протокол* `diarysdk.DiaryLike`

Точка входа: `login`, `student(token)`, `parent(token)`, `aclose()`, `async
with`. Реализации: [`Diary`](#diarysdk.Diary),
[`RemoteDiary`](remote.md#diarysdk.remote.RemoteDiary).

<a id="diarysdk.LoginLike"></a>

### *протокол* `diarysdk.LoginLike`

Вход: `password()`, `esia()`. Реализации: [`Login`](#diarysdk.Login),
[`RemoteLogin`](remote.md#diarysdk.remote.RemoteLogin).

<a id="diarysdk.LoginFlowLike"></a>

### *протокол* `diarysdk.LoginFlowLike`

Незаконченный вход: `kind`, `mfa`, `captcha`, `expires_at`, `submit_code()`,
`answer_captcha()`, `renew_captcha()`, `close()`. Реализации:
[`LoginFlow`](#diarysdk.LoginFlow),
[`RemoteLoginFlow`](remote.md#diarysdk.remote.RemoteLoginFlow).

<a id="diarysdk.StudentLike"></a>

### *протокол* `diarysdk.StudentLike`

Все методы [`Student`](#diarysdk.Student). Реализации: `Student`,
[`RemoteStudent`](remote.md#diarysdk.remote.RemoteStudent).

<a id="diarysdk.ParentLike"></a>

### *протокол* `diarysdk.ParentLike`

Все методы [`Parent`](#diarysdk.Parent). Реализации: `Parent`,
[`RemoteParent`](remote.md#diarysdk.remote.RemoteParent).

*Добавлено в версии 0.2.0.*

## Журнал `httpx`

При импорте SDK добавляет фильтр к глобальному логгеру `httpx`: он скрывает
записи о запросах к дневнику (в их URL бывают идентификаторы ученика). Другие
записи `httpx` и журналы вашего приложения фильтр не трогает.

> [!WARNING]
> Логгер `httpcore` фильтр **не** скрывает: на уровне DEBUG он пишет адреса и
> заголовки соединений. Не включайте DEBUG для `httpcore` там, где журналы
> уходят во внешние системы.
