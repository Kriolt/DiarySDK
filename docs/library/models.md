# `diarysdk.models` — модели ответов

[Документация](../index.md) » [Справочник библиотеки](index.md) » `diarysdk.models`

**Исходный код:** [`diarysdk/models/`](../../diarysdk/models/)

---

Всё, что возвращают методы [`Student`](diarysdk.md#diarysdk.Student) и
[`Parent`](diarysdk.md#diarysdk.Parent), — модели этого пакета. Все они
импортируются из `diarysdk.models` (список — `diarysdk.models.__all__`) и
лежат в модулях `diarysdk.models.<модуль>`; оба адреса правильные.

```python
from diarysdk.models import Homework, Mark, SettingsUpdate
```

## Как устроены модели

Почти все модели — схемы [pydantic](https://docs.pydantic.dev/) (наследники
`pydantic.BaseModel`):

- **Поля необязательные.** Если дневник поля не дал, оно равно `None`.
  Поле в таблице с пометкой **всегда** не бывает `None`. Списки по умолчанию
  пустые, а не `None`.
- **Неизвестные поля отбрасываются**: новое поле в ответе дневника ничего не
  ломает.
- **Ответ другой формы** — например, `null` вместо списка — даёт
  [`UpstreamFormat`](errors.md#diarysdk.errors.UpstreamFormat) с путями
  полей, без значений.
- **«JSON как есть»** — поле, форму которого живые ответы не подтвердили
  (обычно оно всегда было пустым). Оно отдаётся без разбора: `dict`, `list`,
  строка, число или `None`.
- **`class_`.** «class» — зарезервированное слово, поэтому поле называется
  `class_`. В JSON сервиса и в `model_dump(by_alias=True)` оно называется
  `class`.
- **Шкалы.** `value` оценки — строка как в дневнике (`"9"`, `"зч"`). Поля
  `five`, `ten`, `hundred` и `average_five` — пересчёт самого дневника в
  пяти-, десяти- и стобалльную шкалу; своего пересчёта SDK не делает.

Модели [`Avatar`](#diarysdk.models.Avatar),
[`DiaryFile`](#diarysdk.models.DiaryFile) и
[`Captcha`](#diarysdk.models.Captcha) — неизменяемые `dataclass`: в них байты,
которым нечего делать в JSON. Байты не попадают в `repr`.

## Общие части

<a id="diarysdk.models.Subject"></a>

### *модель* `diarysdk.models.Subject`

Предмет.

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id предмета; его принимают `subject()`, `subject_topics()`, `rating(subject=...)` |
| `name` | `str` | название |

<a id="diarysdk.models.PersonName"></a>

### *модель* `diarysdk.models.PersonName`

ФИО. База для моделей людей.

| Поле | Тип | Что это |
| --- | --- | --- |
| `last_name` | `str` | фамилия |
| `first_name` | `str` | имя |
| `middle_name` | `str` | отчество |

<a id="diarysdk.models.SchoolBrief"></a>

### *модель* `diarysdk.models.SchoolBrief`

Школа кратко.

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id школы |
| `name` | `str` | полное название |
| `short_name` | `str` | краткое название |
| `municipality` | `str` | муниципалитет |

<a id="diarysdk.models.ClassUnit"></a>

### *модель* `diarysdk.models.ClassUnit`

Класс ученика.

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | `class_unit_id`: у двух учеников одного класса он одинаковый |
| `name` | `str` | название («10А») |
| `level` | `int` | параллель |

<a id="diarysdk.models.Material"></a>

### *модель* `diarysdk.models.Material`

Учебный материал урока или задания.

| Поле | Тип | Что это |
| --- | --- | --- |
| `title` | `str` | название |
| `url` | `str` | ссылка |
| `description` | `str` | описание |
| `content_type` | `str` | тип содержимого |
| `type_name` | `str` | вид материала, как в дневнике («Вложения») |
| `action_name` | `str` | действие с ним, как в дневнике («Посмотреть») |

## Вход и токен

<a id="diarysdk.models.TokenResponse"></a>

### *модель* `diarysdk.models.TokenResponse`

Ответ сервиса после входа (`200` маршрутов `/v1/auth/*`). Удалённый клиент
превращает его в [`Token`](token.md#diarysdk.Token).

| Поле | Тип | Что это |
| --- | --- | --- |
| `token` | `str` | JWT дневника; **всегда** |
| `expires_at` | `datetime` | срок токена; **всегда** |
| `method` | `"jwt"`, `"password"`, `"esia"` | как получен; **всегда** |

<a id="diarysdk.models.TokenInfo"></a>

### *модель* `diarysdk.models.TokenInfo`

Ответ `GET /v1/auth/token`: что видно из самого JWT, без похода в дневник. Из
ядра его не возвращает ни один метод — те же сведения есть у
[`Token`](token.md#diarysdk.Token). Импортируется и из `diarysdk`.

| Поле | Тип | Что это |
| --- | --- | --- |
| `expires_at` | `datetime` | срок; **всегда** |
| `expires_in` | `int` | секунд до истечения на момент ответа; **всегда** |
| `subject_id` | `str` | `sub` токена |
| `roles` | `list[str]` | id ролей, как у [`Token.roles`](token.md#diarysdk.Token.roles) |

<a id="diarysdk.models.LoginMfa"></a>

### *модель* `diarysdk.models.LoginMfa`

Госуслуги ждут код. Импортируется и из `diarysdk`.

| Поле | Тип | Что это |
| --- | --- | --- |
| `kind` | `"sms"`, `"totp"`, `"max"` | откуда код: SMS, приложение-аутентификатор, мессенджер MAX; **всегда** |
| `contact` | `str` | куда ушёл код, как его маскируют Госуслуги («+7 \*\*\* \*\*\*-\*\*-12»); для `totp` нет; в `repr` не показывается |
| `ttl` | `int` | сколько секунд живёт код; **всегда** |
| `attempts_left` | `int` | сколько попыток осталось; **всегда** |

<a id="diarysdk.models.Captcha"></a>

### *класс данных* `diarysdk.models.Captcha`

Капча Госуслуг для потребителя: картинка или вопрос. Импортируется и из
`diarysdk`.

| Поле | Тип | Что это |
| --- | --- | --- |
| `kind` | `"image"`, `"question"` | вид капчи; **всегда** |
| `image` | `bytes` | картинка, для `kind="image"`; в `repr` не показывается |
| `image_type` | `str` | MIME-тип картинки (`image/png`…) |
| `question` | `str` | текст вопроса, для `kind="question"`; в `repr` не показывается |

<a id="diarysdk.models.LoginCaptcha"></a>

### *модель* `diarysdk.models.LoginCaptcha`

Капча в JSON сервиса: то же, что [`Captcha`](#diarysdk.models.Captcha), но
картинка — строкой base64.

| Поле | Тип | Что это |
| --- | --- | --- |
| `kind` | `"image"`, `"question"` | вид капчи; **всегда** |
| `image_base64` | `str` | картинка в base64 |
| `image_type` | `str` | MIME-тип картинки |
| `question` | `str` | текст вопроса |

<a id="diarysdk.models.LoginStep"></a>

### *модель* `diarysdk.models.LoginStep`

Вход через Госуслуги не закончен: тело ответа `202`. Удалённый клиент
превращает его в [`RemoteLoginFlow`](remote.md#diarysdk.remote.RemoteLoginFlow).

| Поле | Тип | Что это |
| --- | --- | --- |
| `flow_id` | `str` | id потока для маршрутов `/v1/auth/esia/{flow_id}/...`; **всегда** |
| `step` | `"mfa"`, `"captcha"` | чего ждёт вход; **всегда** |
| `expires_at` | `datetime` | когда поток истечёт (5 минут с последнего шага); **всегда** |
| `mfa` | [`LoginMfa`](#diarysdk.models.LoginMfa) | для `step="mfa"` |
| `captcha` | [`LoginCaptcha`](#diarysdk.models.LoginCaptcha) | для `step="captcha"` |

## Профиль

<a id="diarysdk.models.Me"></a>

### *модель* `diarysdk.models.Me`

Результат [`Student.me()`](diarysdk.md#diarysdk.Student.me).

| Поле | Тип | Что это |
| --- | --- | --- |
| `person` | [`MePerson`](#diarysdk.models.MePerson) | ученик; **всегда** |
| `school` | [`SchoolBrief`](#diarysdk.models.SchoolBrief) | школа; **всегда** |
| `class_` | [`ClassUnit`](#diarysdk.models.ClassUnit) | класс; в JSON — `class`; **всегда** |
| `study_profile` | `str` | профиль обучения из названий групп («ф.-м.») |
| `sections` | `list[`[`Section`](#diarysdk.models.Section)`]` | кружки и секции |
| `enrolled_on` | `date` | дата зачисления |
| `token` | [`TokenExpiry`](#diarysdk.models.TokenExpiry) | срок токена; **всегда** |

<a id="diarysdk.models.MePerson"></a>

### *модель* `diarysdk.models.MePerson`

Ученик в [`Me`](#diarysdk.models.Me).

| Поле | Тип | Что это |
| --- | --- | --- |
| `last_name`, `first_name`, `middle_name` | `str` | ФИО, из [`PersonName`](#diarysdk.models.PersonName) |
| `sex` | `str` | пол, как в дневнике |
| `age` | `int` | возраст |
| `guid` | `str` | `contingent_guid` — тот же GUID, что у ученика в рейтинге одноклассников ([`RatingEntry.guid`](#diarysdk.models.RatingEntry)) |

<a id="diarysdk.models.Section"></a>

### *модель* `diarysdk.models.Section`

Кружок или секция.

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id |
| `name` | `str` | название |

<a id="diarysdk.models.TokenExpiry"></a>

### *модель* `diarysdk.models.TokenExpiry`

Срок токена в [`Me`](#diarysdk.models.Me) и
[`ParentMe`](#diarysdk.models.ParentMe).

| Поле | Тип | Что это |
| --- | --- | --- |
| `expires_at` | `datetime` | срок; **всегда** |

<a id="diarysdk.models.Avatar"></a>

### *класс данных* `diarysdk.models.Avatar`

Результат `avatar()`: сама картинка. Импортируется и из `diarysdk`.

| Поле | Тип | Что это |
| --- | --- | --- |
| `content` | `bytes` | байты картинки; **всегда**; в `repr` не показываются |
| `content_type` | `str` | MIME-тип; **всегда** |

## Родитель

<a id="diarysdk.models.ParentMe"></a>

### *модель* `diarysdk.models.ParentMe`

Результат [`Parent.me()`](diarysdk.md#diarysdk.Parent.me). СНИЛС и документы
— в [`Parent.identity()`](diarysdk.md#diarysdk.Parent.identity).

*Добавлено в версии 0.2.0.*

| Поле | Тип | Что это |
| --- | --- | --- |
| `first_name`, `last_name`, `middle_name` | `str` | ФИО |
| `type` | `str` | тип профиля, как в дневнике |
| `email` | `str` | почта |
| `phone` | `str` | телефон |
| `token` | [`TokenExpiry`](#diarysdk.models.TokenExpiry) | срок токена; **всегда** |

<a id="diarysdk.models.Child"></a>

### *модель* `diarysdk.models.Child`

Ученик, доступный родителю.

*Добавлено в версии 0.2.0.*

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id ученика для [`Parent.student(id)`](diarysdk.md#diarysdk.Parent.student) и `child_id` сервиса; **всегда** |
| `first_name`, `last_name`, `middle_name` | `str` | ФИО |
| `school` | [`SchoolBrief`](#diarysdk.models.SchoolBrief) | школа; **всегда** |
| `class_name` | `str` | класс («10А») |
| `is_legal_representative` | `bool` | родитель — законный представитель |

<a id="diarysdk.models.JournalAck"></a>

### *модель* `diarysdk.models.JournalAck`

Отметка родителя «ознакомлен с дневником» за неделю.

*Добавлено в версии 0.2.0.*

| Поле | Тип | Что это |
| --- | --- | --- |
| `week` | `date` | понедельник недели; **всегда** |
| `created_at` | `datetime` | когда отметили (по Москве) |
| `child_id` | `int` | ученик; **всегда** |

## Школа

<a id="diarysdk.models.School"></a>

### *модель* `diarysdk.models.School`

Результат [`Student.school()`](diarysdk.md#diarysdk.Student.school).

| Поле | Тип | Что это |
| --- | --- | --- |
| `name` | `str` | название |
| `type` | `str` | тип учреждения |
| `principal` | `str` | директор |
| `address` | `str` | адрес |
| `phone` | `str` | телефон |
| `email` | `str` | почта |
| `website` | `str` | сайт |
| `classroom_teachers` | `list[`[`PersonName`](#diarysdk.models.PersonName)`]` | классные руководители |
| `teachers` | `list[`[`Teacher`](#diarysdk.models.Teacher)`]` | учителя |
| `branches` | `list[`[`Branch`](#diarysdk.models.Branch)`]` | корпуса |
| `id` | `int` | id школы |
| `county` | `str` | округ из адреса школы |
| `district` | `str` | район из адреса школы |

<a id="diarysdk.models.Teacher"></a>

### *модель* `diarysdk.models.Teacher`

Учитель в [`School`](#diarysdk.models.School).

| Поле | Тип | Что это |
| --- | --- | --- |
| `last_name`, `first_name`, `middle_name` | `str` | ФИО, из [`PersonName`](#diarysdk.models.PersonName) |
| `subjects` | `list[str]` | названия предметов |

<a id="diarysdk.models.Branch"></a>

### *модель* `diarysdk.models.Branch`

Корпус школы.

| Поле | Тип | Что это |
| --- | --- | --- |
| `name` | `str` | название |
| `address` | `str` | адрес |
| `is_main` | `bool` | главный корпус |
| `building_id` | `int` | id здания |
| `is_student_building` | `bool` | признак дневника `is_student_building` |
| `type` | `str` | тип, как в дневнике |

<a id="diarysdk.models.SchoolTeacher"></a>

### *модель* `diarysdk.models.SchoolTeacher`

Учитель из справочника школы (на сайте — «Учителя»). Результат
[`school_teachers()`](diarysdk.md#diarysdk.Student.school_teachers).

*Добавлено в версии 0.2.0.*

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id; **всегда** |
| `name` | `str` | ФИО одной строкой |
| `type` | `str` | как в дневнике: `"teacher"` и т. п. |
| `roles` | `list[str]` | роли |
| `subjects` | `list[`[`Subject`](#diarysdk.models.Subject)`]` | предметы |

## Оценки

<a id="diarysdk.models.Mark"></a>

### *модель* `diarysdk.models.Mark`

Оценка. Результат [`marks()`](diarysdk.md#diarysdk.Student.marks); тот же
класс — в расписании, уроке и предметах.

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id для [`mark()`](diarysdk.md#diarysdk.Student.mark) |
| `date` | `date` | дата |
| `subject` | [`Subject`](#diarysdk.models.Subject) | предмет |
| `value` | `str` | оценка как в дневнике: «9», бывает «зч» |
| `scale` | `str` | система оценивания |
| `five` | `float` | пересчёт дневника в пятибалльную шкалу |
| `ten` | `float` | пересчёт дневника в десятибалльную шкалу |
| `hundred` | `float` | пересчёт дневника в стобалльную шкалу |
| `nmax` | `float` | наибольшая оценка шкалы |
| `weight` | `int` | вес |
| `control_form` | `str` | форма контроля («Контрольная работа») |
| `comment` | `str` | комментарий учителя |
| `is_exam` | `bool` | экзаменационная |
| `is_point` | `bool` | «точка» — оценку нужно исправить |
| `point_date` | `date` | до какого числа исправить |
| `has_files` | `bool` | к оценке приложены файлы |
| `created_at` | `datetime` | когда поставлена |
| `updated_at` | `datetime` | когда изменена |
| `criteria` | JSON как есть | критерии; в наблюдениях всегда пустой список |

<a id="diarysdk.models.MarkDetail"></a>

### *модель* `diarysdk.models.MarkDetail`

Одна оценка подробно. Результат
[`mark()`](diarysdk.md#diarysdk.Student.mark).

> [!NOTE]
> Источник живым ответом не подтверждён; форма — по другим клиентам дневника.

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id |
| `value` | `str` | оценка как в дневнике |
| `five` | `float` | пересчёт дневника в пятибалльную шкалу |
| `weight` | `int` | вес |
| `control_form` | `str` | форма контроля |
| `comment` | `str` | комментарий |
| `is_exam` | `bool` | экзаменационная |
| `is_point` | `bool` | «точка» |
| `point_date` | `date` | до какого числа исправить |
| `date` | `date` | дата |
| `teacher` | [`PersonName`](#diarysdk.models.PersonName) | учитель |
| `lesson` | [`MarkLesson`](#diarysdk.models.MarkLesson) | урок |
| `class_results` | [`ClassResults`](#diarysdk.models.ClassResults) | итоги класса за эту работу: только числа |
| `criteria`, `history`, `result_files` | JSON как есть | форму живой ответ не подтвердил |

<a id="diarysdk.models.MarkLesson"></a>

### *модель* `diarysdk.models.MarkLesson`

Урок, на котором поставлена оценка.

| Поле | Тип | Что это |
| --- | --- | --- |
| `topic` | `str` | тема |
| `schedule_item_id` | `int` | id урока для [`lesson()`](diarysdk.md#diarysdk.Student.lesson) |

<a id="diarysdk.models.ClassResults"></a>

### *модель* `diarysdk.models.ClassResults`

Итоги класса за работу.

| Поле | Тип | Что это |
| --- | --- | --- |
| `total_students` | `int` | учеников в классе |
| `distribution` | `list[`[`MarkDistribution`](#diarysdk.models.MarkDistribution)`]` | распределение оценок |

<a id="diarysdk.models.MarkDistribution"></a>

### *модель* `diarysdk.models.MarkDistribution`

Сколько учеников класса получили оценку `value`: число и доля, без имён и id.

| Поле | Тип | Что это |
| --- | --- | --- |
| `value` | `str` | оценка |
| `students` | `int` | сколько учеников |
| `percent` | `int` | доля класса, % |

<a id="diarysdk.models.FinalMark"></a>

### *модель* `diarysdk.models.FinalMark`

Годовая оценка по предмету. Результат
[`final_marks()`](diarysdk.md#diarysdk.Student.final_marks).

| Поле | Тип | Что это |
| --- | --- | --- |
| `subject` | [`Subject`](#diarysdk.models.Subject) | предмет |
| `year_mark` | `str` | годовая оценка как в дневнике («7», «Зч»); `None` — оценки нет |
| `attestation_mark` | `str` | промежуточная аттестация |
| `training_camp_mark` | `str` | учебные сборы |

<a id="diarysdk.models.AcademicDebt"></a>

### *модель* `diarysdk.models.AcademicDebt`

Академическая задолженность по предмету. Результат
[`academic_debts()`](diarysdk.md#diarysdk.Student.academic_debts).

> [!NOTE]
> Форма не подтверждена: живые ответы были пустыми, поля — по тому, что
> читает сайт.

*Добавлено в версии 0.2.0.*

| Поле | Тип | Что это |
| --- | --- | --- |
| `subject` | [`Subject`](#diarysdk.models.Subject) | предмет; **всегда** |
| `original_final_mark` | JSON как есть | итоговая оценка, по которой возник долг |
| `attested` | `bool` | «аттестован»: есть итоговая или оценка хоть в одной попытке; **всегда** |
| `attempts` | JSON как есть | попытки пересдачи |

## Предметы

<a id="diarysdk.models.SubjectSummary"></a>

### *модель* `diarysdk.models.SubjectSummary`

Предмет в [`subjects()`](diarysdk.md#diarysdk.Student.subjects).

| Поле | Тип | Что это |
| --- | --- | --- |
| `subject` | [`Subject`](#diarysdk.models.Subject) | предмет; **всегда** |
| `average` | `float` | средний **самого ученика** по всем оценкам года, пятибалльный; это не средний класса |
| `dynamic` | `str` | динамика, как в дневнике |
| `year_mark` | `str` | годовая оценка |
| `periods` | `list[`[`Period`](#diarysdk.models.Period)`]` | периоды (четверти, полугодия) |

<a id="diarysdk.models.Period"></a>

### *модель* `diarysdk.models.Period`

Учебный период предмета.

| Поле | Тип | Что это |
| --- | --- | --- |
| `title` | `str` | название («1 четверть») |
| `start` | `date` | начало |
| `end` | `date` | конец |
| `average` | `float` | средний за период, пятибалльный; без оценок — `None` |
| `final_mark` | `str` | итоговая оценка периода |
| `marks` | `list[`[`Mark`](#diarysdk.models.Mark)`]` | оценки |
| `marks_count` | `int` | сколько оценок |
| `dynamic` | `str` | динамика |
| `target` | [`Target`](#diarysdk.models.Target) | цель периода |

<a id="diarysdk.models.Target"></a>

### *модель* `diarysdk.models.Target`

Цель периода из дневника: до оценки `value` осталось `remain` оценок.

| Поле | Тип | Что это |
| --- | --- | --- |
| `value` | `int` | целевая оценка |
| `round` | `str` | правило округления, как в дневнике |
| `remain` | `int` | сколько оценок осталось |
| `paths` | `list[`[`TargetPath`](#diarysdk.models.TargetPath)`]` | пути к цели |

<a id="diarysdk.models.TargetPath"></a>

### *модель* `diarysdk.models.TargetPath`

Один путь к цели: получить `remain` оценок `value` весом `weight`.

| Поле | Тип | Что это |
| --- | --- | --- |
| `value` | `int` | оценка |
| `weight` | `int` | вес |
| `remain` | `int` | сколько таких оценок |

<a id="diarysdk.models.SubjectDetail"></a>

### *модель* `diarysdk.models.SubjectDetail`

Результат [`subject()`](diarysdk.md#diarysdk.Student.subject).

| Поле | Тип | Что это |
| --- | --- | --- |
| `subject_id` | `int` | id предмета |
| `subject_name` | `str` | название |
| `average_five` | `float` | средний, пятибалльный; «0.00» и не число — `None` |
| `average_by_all` | `float` | средний по всем оценкам года, пятибалльный |
| `dynamic` | `str` | динамика |
| `periods` | `list[`[`SubjectDetailPeriod`](#diarysdk.models.SubjectDetailPeriod)`]` | периоды |

<a id="diarysdk.models.SubjectDetailPeriod"></a>

### *модель* `diarysdk.models.SubjectDetailPeriod`

Период в [`SubjectDetail`](#diarysdk.models.SubjectDetail): поля дневника как
есть.

| Поле | Тип | Что это |
| --- | --- | --- |
| `title` | `str` | название |
| `start` | `date` | начало |
| `end` | `date` | конец |
| `value` | `str` | средний строкой, как в дневнике («4.50»); без оценок — «0.00» |
| `fixed_value` | `str` | итоговая оценка периода, если выставлена |
| `dynamic` | `str` | динамика |
| `count` | `int` | сколько оценок |
| `target` | [`Target`](#diarysdk.models.Target) | до какой оценки и сколько каких оценок осталось |
| `marks` | `list[`[`Mark`](#diarysdk.models.Mark)`]` | оценки |

## Рейтинг

Места в рейтинге дневника плотные: при равном среднем место общее, и следом
идёт следующее без пропуска (два вторых, следом третий). Поэтому рядом с
`place` есть `ahead` — сколько учеников стоят выше; `ahead + 1` — место «с
пропусками» (два вторых, следом четвёртый). Поля с суффиксом `_30` — те же
величины за последние 30 дней, `previous_…` — прошлое значение.

<a id="diarysdk.models.Rating"></a>

### *модель* `diarysdk.models.Rating`

Результат [`rating()`](diarysdk.md#diarysdk.Student.rating).

| Поле | Тип | Что это |
| --- | --- | --- |
| `enabled` | `bool` | рейтинг включён в школе; если `False`, остальные поля `None`; **всегда** |
| `date` | `date` | на какую дату |
| `total` | `int` | учеников в рейтинге (не наибольшее место) |
| `class_average_five` | `float` | средний класса — среднее по всем `average_five` |
| `me` | [`RatingMe`](#diarysdk.models.RatingMe) | сам ученик |
| `class_` | `list[`[`RatingEntry`](#diarysdk.models.RatingEntry)`]` | весь класс; в JSON — `class` |

<a id="diarysdk.models.RatingMe"></a>

### *модель* `diarysdk.models.RatingMe`

Место ученика.

| Поле | Тип | Что это |
| --- | --- | --- |
| `place`, `place_30` | `int` | место |
| `average_five`, `average_five_30` | `float` | средний, пятибалльный |
| `trend`, `trend_30` | `str` | направление, как в дневнике |
| `rank_status_30` | `str` | статус места, как в дневнике |
| `previous_place`, `previous_place_30` | `int` | прошлое место |
| `previous_average_five`, `previous_average_five_30` | `float` | прошлый средний |
| `ahead`, `ahead_30` | `int` | сколько учеников стоят выше |

<a id="diarysdk.models.RatingEntry"></a>

### *модель* `diarysdk.models.RatingEntry`

Одноклассник (или сам ученик) в рейтинге класса.

| Поле | Тип | Что это |
| --- | --- | --- |
| `is_me` | `bool` | это сам ученик; **всегда** (по умолчанию `False`) |
| `guid` | `str` | GUID одноклассника — тот же, что у него в [`MePerson.guid`](#diarysdk.models.MePerson) |
| `image_id` | `int` | id его аватарки |
| `place`, `place_30` | `int` | место |
| `average_five`, `average_five_30` | `float` | средний, пятибалльный |
| `trend`, `trend_30` | `str` | направление |
| `rank_status`, `rank_status_30` | `str` | статус места |
| `previous_place`, `previous_place_30` | `int` | прошлое место |
| `previous_average_five`, `previous_average_five_30` | `float` | прошлый средний |
| `ahead`, `ahead_30` | `int` | сколько учеников стоят выше; нет места — `None` |
| `attestation_period_id`, `period_id`, `module_id` | `int` | период рейтинга, коды дневника |

<a id="diarysdk.models.SubjectRating"></a>

### *модель* `diarysdk.models.SubjectRating`

Место и средний самого ученика по предмету. Результат
[`rating_subjects()`](diarysdk.md#diarysdk.Student.rating_subjects). Среднего
класса здесь нет: дневник его в этом ответе не даёт. Весь класс по одному
предмету — `rating(subject=id)`.

| Поле | Тип | Что это |
| --- | --- | --- |
| `subject` | [`Subject`](#diarysdk.models.Subject) | предмет; **всегда** |
| `place`, `place_30` | `int` | место |
| `average_five`, `average_five_30` | `float` | средний, пятибалльный |
| `trend`, `trend_30` | `str` | направление |
| `rank_status`, `rank_status_30` | `str` | статус места |
| `attestation_period_id`, `period_id`, `module_id` | `int` | период рейтинга, коды дневника |

<a id="diarysdk.models.RatingPoint"></a>

### *модель* `diarysdk.models.RatingPoint`

Точка истории. Результат
[`rating_history()`](diarysdk.md#diarysdk.Student.rating_history).

| Поле | Тип | Что это |
| --- | --- | --- |
| `date` | `date` | день |
| `place` | `int` | место в этот день |

## Расписание и уроки

<a id="diarysdk.models.ScheduleItem"></a>

### *модель* `diarysdk.models.ScheduleItem`

Урок или событие календаря. Результат
[`schedule()`](diarysdk.md#diarysdk.Student.schedule); подробности урока —
[`lesson(id)`](diarysdk.md#diarysdk.Student.lesson).

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id для `lesson()` |
| `date` | `date` | день |
| `start` | `datetime` | начало |
| `end` | `datetime` | конец |
| `subject` | [`Subject`](#diarysdk.models.Subject) | предмет |
| `room` | `str` | кабинет |
| `lesson_type` | `str` | тип урока, как в дневнике |
| `course_lesson_type` | `str` | тип занятия курса, как в дневнике |
| `is_cancelled` | `bool` | отменён |
| `is_replaced` | `bool` | замена |
| `replaced_teacher_id` | `int` | кого заменяют |
| `marks` | `list[`[`Mark`](#diarysdk.models.Mark)`]` | оценки за урок |
| `homework` | `list[`[`HomeworkBrief`](#diarysdk.models.HomeworkBrief)`]` | ДЗ к уроку |
| `homework_counts` | [`HomeworkCounts`](#diarysdk.models.HomeworkCounts) | сколько заданий и сколько выполнено |
| `health_status` | `str` | статус здоровья, как в дневнике |
| `is_missed` | `bool` | пропущен |
| `absence_reason_id`, `nonattendance_reason_id` | `int` | причина отсутствия, коды дневника |
| `link_to_join` | `str` | ссылка на дистанционный урок |
| `lesson_form` | JSON как есть | в наблюдениях всегда `None` |
| `source` | `str` | откуда событие: `PLAN` — урок из расписания, `EC` — событие календаря |
| `source_id` | `str` | id в источнике |

<a id="diarysdk.models.HomeworkBrief"></a>

### *модель* `diarysdk.models.HomeworkBrief`

ДЗ к уроку кратко.

| Поле | Тип | Что это |
| --- | --- | --- |
| `text` | `str` | текст задания |
| `materials` | `list[`[`Material`](#diarysdk.models.Material)`]` | материалы |

<a id="diarysdk.models.HomeworkCounts"></a>

### *модель* `diarysdk.models.HomeworkCounts`

Счётчики заданий урока.

| Поле | Тип | Что это |
| --- | --- | --- |
| `total` | `int` | всего |
| `executed` | `int` | выполнено |
| `presence_status_id` | `int` | статус присутствия, код дневника |

<a id="diarysdk.models.Lesson"></a>

### *модель* `diarysdk.models.Lesson`

Урок подробно. Результат [`lesson()`](diarysdk.md#diarysdk.Student.lesson).

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id |
| `date` | `date` | день |
| `start`, `end` | `datetime` | начало и конец |
| `subject` | [`Subject`](#diarysdk.models.Subject) | предмет |
| `room` | `str` | кабинет |
| `building` | `str` | корпус |
| `topic` | `str` | тема урока |
| `theme` | [`Theme`](#diarysdk.models.Theme) | тема с вложенными разделами |
| `teacher` | [`LessonTeacher`](#diarysdk.models.LessonTeacher) | учитель |
| `marks` | `list[`[`Mark`](#diarysdk.models.Mark)`]` | оценки |
| `homework` | `list[`[`HomeworkBrief`](#diarysdk.models.HomeworkBrief)`]` | ДЗ |
| `materials` | `list[`[`Material`](#diarysdk.models.Material)`]` | материалы |
| `is_missed` | `bool` | пропущен |
| `nonattendance_reason_id` | `int` | причина отсутствия, код дневника |
| `comment` | `str` | комментарий |
| `is_virtual` | `bool` | дистанционный |
| `lesson_type`, `lesson_education_type` | `str` | тип урока, как в дневнике |
| `plan_id` | `int` | id плана |
| `group_id` | `int` | id учебной группы |
| `disease_status`, `is_remote`, `control`, `evaluation`, `teacher_comments`, `student_work`, `theme_mastery`, `kr_attachments`, `content` | JSON как есть | в наблюдениях всегда пустые |

<a id="diarysdk.models.LessonTeacher"></a>

### *модель* `diarysdk.models.LessonTeacher`

Учитель урока.

| Поле | Тип | Что это |
| --- | --- | --- |
| `last_name`, `first_name`, `middle_name` | `str` | ФИО, из [`PersonName`](#diarysdk.models.PersonName) |
| `sex` | `str` | пол |
| `birth_date` | `date` | дата рождения |
| `user_id` | `int` | id пользователя |

<a id="diarysdk.models.Theme"></a>

### *модель* `diarysdk.models.Theme`

Тема урока и вложенные разделы любой глубины.

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id |
| `title` | `str` | название |
| `average_mark` | `float` | средний по теме |
| `oge_task`, `ege_task` | JSON как есть | задания ОГЭ и ЕГЭ: то `None`, то список строк |
| `frames` | `list[`[`Theme`](#diarysdk.models.Theme)`]` | вложенные разделы |

<a id="diarysdk.models.PeriodDay"></a>

### *модель* `diarysdk.models.PeriodDay`

День календаря периодов: каникулы, праздники. Результат
[`periods()`](diarysdk.md#diarysdk.Student.periods).

| Поле | Тип | Что это |
| --- | --- | --- |
| `date` | `date` | день |
| `type` | `str` | тип дня, как в дневнике |
| `title` | `str` | название |
| `description` | `str` | описание |
| `events` | JSON как есть | события дня |

## Домашние задания

<a id="diarysdk.models.Homework"></a>

### *модель* `diarysdk.models.Homework`

Домашнее задание. Результат
[`homework()`](diarysdk.md#diarysdk.Student.homework).

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id для [`homework_done()`](diarysdk.md#diarysdk.Student.homework_done) — строго `homework_entry_student_id` дневника; `None` — отметить задание нельзя |
| `due` | `date` | дата сдачи; по ней задаётся период `homework()` |
| `assigned_on` | `date` | когда задано |
| `subject` | [`Subject`](#diarysdk.models.Subject) | предмет |
| `text` | `str` | текст задания |
| `materials` | `list[`[`Material`](#diarysdk.models.Material)`]` | материалы |
| `attachments` | `list[`[`Attachment`](#diarysdk.models.Attachment)`]` | вложения |
| `is_done` | `bool` | отмечено выполненным |
| `has_teacher_answer` | `bool` | есть ответ учителя |
| `type` | `str` | тип, как в дневнике |
| `group_id` | `int` | id учебной группы |
| `homework_id`, `entry_id` | `int` | другие id дневника; для отметки не годятся |
| `lesson_at` | `datetime` | начало урока, к которому задано |
| `created_at`, `updated_at` | `datetime` | когда создано и изменено |
| `comments`, `written_answer` | JSON как есть | в наблюдениях всегда пустые |

<a id="diarysdk.models.Attachment"></a>

### *модель* `diarysdk.models.Attachment`

Вложение к заданию.

| Поле | Тип | Что это |
| --- | --- | --- |
| `name` | `str` | имя файла |
| `url` | `str` | ссылка |

## Учебный план и программы

<a id="diarysdk.models.Curriculum"></a>

### *модель* `diarysdk.models.Curriculum`

Учебный план параллели. Результат
[`curriculum()`](diarysdk.md#diarysdk.Student.curriculum).

| Поле | Тип | Что это |
| --- | --- | --- |
| `title` | `str` | название |
| `short_name` | `str` | краткое название |
| `education_level` | `str` | уровень образования |
| `education_form` | `str` | форма обучения |
| `class_level_id` | `int` | параллель |
| `hours` | `int` | часов всего |
| `days_in_week` | `int` | учебных дней в неделю |
| `is_adapted` | `bool` | адаптированный план |
| `comments`, `specialization`, `study_profile` | JSON как есть | форма не подтверждена |
| `sections` | `list[`[`CurriculumSection`](#diarysdk.models.CurriculumSection)`]` | разделы |
| `weeks` | `list[`[`CurriculumWeek`](#diarysdk.models.CurriculumWeek)`]` | недели учебного года |

<a id="diarysdk.models.CurriculumSection"></a>

### *модель* `diarysdk.models.CurriculumSection`

Раздел плана: область знаний и её предметы.

| Поле | Тип | Что это |
| --- | --- | --- |
| `knowledge_field` | `str` | область знаний |
| `subjects` | `list[`[`CurriculumSubject`](#diarysdk.models.CurriculumSubject)`]` | предметы |

<a id="diarysdk.models.CurriculumSubject"></a>

### *модель* `diarysdk.models.CurriculumSubject`

Предмет учебного плана.

| Поле | Тип | Что это |
| --- | --- | --- |
| `subject_id` | `int` | id предмета |
| `subject_name` | `str` | название |
| `parent_subject_id` | `int` | родительский предмет (у подпредмета раздела) |
| `total_hours` | `int` | часов за год |
| `passed_hours` | `int` | часов пройдено |
| `min_hours_per_week`, `max_hours_per_week` | `int` | часов в неделю |
| `teachers` | `list[str]` | учителя |
| `weeks` | `list[`[`CurriculumSubjectWeek`](#diarysdk.models.CurriculumSubjectWeek)`]` | часы по неделям |

<a id="diarysdk.models.CurriculumSubjectWeek"></a>

### *модель* `diarysdk.models.CurriculumSubjectWeek`

Часы предмета в неделю учебного года.

| Поле | Тип | Что это |
| --- | --- | --- |
| `week_number` | `int` | номер недели |
| `hours` | `int` | часов |

<a id="diarysdk.models.CurriculumWeek"></a>

### *модель* `diarysdk.models.CurriculumWeek`

Неделя учебного года.

| Поле | Тип | Что это |
| --- | --- | --- |
| `week_number` | `int` | номер |
| `begin`, `end` | `date` | границы |
| `hours` | `int` | часов |
| `days` | `int` | учебных дней |

<a id="diarysdk.models.ProgramModule"></a>

### *модель* `diarysdk.models.ProgramModule`

Раздел рабочей программы группы (на сайте — «Рабочие программы»). Результат
[`work_program()`](diarysdk.md#diarysdk.Student.work_program).

*Добавлено в версии 0.2.0.*

| Поле | Тип | Что это |
| --- | --- | --- |
| `title` | `str` | название |
| `ordinal` | `int` | порядковый номер |
| `subject_id` | `int` | id предмета |
| `topics` | `list[`[`ProgramTopic`](#diarysdk.models.ProgramTopic)`]` | темы |

<a id="diarysdk.models.ProgramTopic"></a>

### *модель* `diarysdk.models.ProgramTopic`

Тема раздела рабочей программы.

*Добавлено в версии 0.2.0.*

| Поле | Тип | Что это |
| --- | --- | --- |
| `title` | `str` | название |
| `ordinal` | `int` | порядковый номер |
| `lessons` | `list[`[`ProgramLesson`](#diarysdk.models.ProgramLesson)`]` | уроки |

<a id="diarysdk.models.ProgramLesson"></a>

### *модель* `diarysdk.models.ProgramLesson`

Урок рабочей программы.

*Добавлено в версии 0.2.0.*

| Поле | Тип | Что это |
| --- | --- | --- |
| `title` | `str` | название |
| `ordinal` | `int` | порядковый номер |
| `date` | `date` | дата |
| `lesson_id` | `int` | id для [`lesson()`](diarysdk.md#diarysdk.Student.lesson), если урок уже в расписании |
| `oge_tasks`, `ege_tasks` | `list[str]` | задания ОГЭ и ЕГЭ |

<a id="diarysdk.models.SubjectTopic"></a>

### *модель* `diarysdk.models.SubjectTopic`

Тема предмета (тематическая рамка) и её результаты. Результат
[`subject_topics()`](diarysdk.md#diarysdk.Student.subject_topics).

*Добавлено в версии 0.2.0.*

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id |
| `title` | `str` | название |
| `results` | `list[`[`TopicResult`](#diarysdk.models.TopicResult)`]` | ожидаемые результаты |

<a id="diarysdk.models.TopicResult"></a>

### *модель* `diarysdk.models.TopicResult`

Ожидаемый результат по теме.

*Добавлено в версии 0.2.0.*

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id |
| `text` | `str` | формулировка для семьи |
| `type` | `str` | вид результата, как в дневнике |
| `mandatory` | `str` | обязательность, как в дневнике |

<a id="diarysdk.models.ControlWork"></a>

### *модель* `diarysdk.models.ControlWork`

Контрольная работа. Результат
[`control_works()`](diarysdk.md#diarysdk.Student.control_works).

> [!NOTE]
> Форма не подтверждена: живые ответы были пустыми, поля — по тому, что
> читает сайт («Контрольные работы»).

*Добавлено в версии 0.2.0.*

| Поле | Тип | Что это |
| --- | --- | --- |
| `date` | `date` | дата |
| `subject` | [`Subject`](#diarysdk.models.Subject) | предмет; **всегда** |
| `form` | `str` | форма работы |
| `theme` | `str` | тема |
| `lesson_id` | `int` | id урока |
| `mark` | `str` | оценка |
| `is_absent` | `bool` | ученик отсутствовал |
| `is_success` | `bool` | признак успеха, как на сайте |

## Экзамены, справки, файлы

<a id="diarysdk.models.Exam"></a>

### *модель* `diarysdk.models.Exam`

Результат ГИА. Результат [`exams()`](diarysdk.md#diarysdk.Student.exams).

| Поле | Тип | Что это |
| --- | --- | --- |
| `kind` | `str` | ОГЭ, ЕГЭ или пробный — как пишет портал |
| `subject` | `str` | предмет |
| `date` | `date` | дата |
| `score` | `int` или `float` | баллы |
| `mark` | `str` | оценка |

<a id="diarysdk.models.Certificate"></a>

### *модель* `diarysdk.models.Certificate`

Заявка на справку об обучении. Результат
[`certificates()`](diarysdk.md#diarysdk.Student.certificates).

> [!NOTE]
> Форма не подтверждена: живые списки были пустыми, поля — по тому, что
> читает сайт.

*Добавлено в версии 0.2.0.*

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` или `str` | id заявки |
| `status_id` | `int` | статус, код дневника |
| `status` | `str` | название статуса из справочника дневника («Сформирована») |
| `purpose` | `str` | назначение справки |
| `requested_on` | `date` | когда заказана |
| `issued_on` | `date` | когда выдана |
| `valid_until` | `date` | действительна до |

<a id="diarysdk.models.DiaryFile"></a>

### *класс данных* `diarysdk.models.DiaryFile`

Файл от дневника. Результат
[`final_marks_file()`](diarysdk.md#diarysdk.Student.final_marks_file).

*Добавлено в версии 0.2.0.*

| Поле | Тип | Что это |
| --- | --- | --- |
| `content` | `bytes` | байты; **всегда**; в `repr` не показываются |
| `content_type` | `str` | MIME-тип; **всегда** |
| `filename` | `str` | имя для сохранения («final-marks-2025.pdf») |

## Уведомления

<a id="diarysdk.models.Notification"></a>

### *модель* `diarysdk.models.Notification`

Запись ленты дневника: что поменялось в оценках и ДЗ. Результат
[`notifications()`](diarysdk.md#diarysdk.Student.notifications).

| Поле | Тип | Что это |
| --- | --- | --- |
| `at` | `datetime` | когда |
| `event_type` | `str` | тип события, как в дневнике |
| `subject_name` | `str` | предмет |
| `teacher_name` | `str` | учитель |
| `author_profile_id` | `int` | профиль автора |
| `lesson_date` | `date` | дата урока |
| `mark` | [`NotificationMark`](#diarysdk.models.NotificationMark) | есть, если в записи пришло хоть одно поле оценки |
| `homework` | [`NotificationHomework`](#diarysdk.models.NotificationHomework) | есть, если в записи пришло хоть одно поле ДЗ |

<a id="diarysdk.models.NotificationMark"></a>

### *модель* `diarysdk.models.NotificationMark`

Оценка в записи ленты: что было и что стало.

| Поле | Тип | Что это |
| --- | --- | --- |
| `old` | `str` | прежняя оценка |
| `new` | `str` | новая оценка |
| `weight` | `int` | вес |
| `is_exam` | `bool` | экзаменационная |
| `control_form` | `str` | форма контроля |

<a id="diarysdk.models.NotificationHomework"></a>

### *модель* `diarysdk.models.NotificationHomework`

ДЗ в записи ленты.

| Поле | Тип | Что это |
| --- | --- | --- |
| `description` | `str` | новое описание |
| `assigned_on` | `date` | когда задано |
| `due` | `date` | срок сдачи |

## Настройки

<a id="diarysdk.models.Settings"></a>

### *модель* `diarysdk.models.Settings`

Настройки приложения. Результат
[`settings()`](diarysdk.md#diarysdk.Student.settings); не задавались — все
поля `None`.

| Поле | Тип | Что это |
| --- | --- | --- |
| `goal` | `bool` | настройка цели; справочника значений нет |
| `theme` | [`SettingsTheme`](#diarysdk.models.SettingsTheme) | оформление; **всегда** |
| `schedule_type` | `str` | вид расписания: `compact` или `full` |
| `estimation_type` | `str` | вид оценивания, справочника значений нет; не записывается |

<a id="diarysdk.models.SettingsTheme"></a>

### *модель* `diarysdk.models.SettingsTheme`

Оформление. Значения — строками, как пришли.

| Поле | Тип | Что это |
| --- | --- | --- |
| `type` | `str` | `dark` или `light` |
| `is_automatic` | `bool` | тема по системе |
| `color_pattern` | `str` | `indigo`, `violet` или `pink` |

<a id="diarysdk.models.SettingsUpdate"></a>

### *модель* `diarysdk.models.SettingsUpdate`

Что поменять в [`update_settings()`](diarysdk.md#diarysdk.Student.update_settings).
Нужно хотя бы одно поле; `None` и лишние поля — ошибка проверки
(`pydantic.ValidationError` при создании, `400` у сервиса).

| Поле | Тип | Что это |
| --- | --- | --- |
| `goal` | `bool` | цель |
| `theme` | [`SettingsThemeUpdate`](#diarysdk.models.SettingsThemeUpdate) | оформление |
| `schedule_type` | `"compact"`, `"full"` | вид расписания |

<a id="diarysdk.models.SettingsUpdate.changes"></a>

#### *метод* `changes()`

Плоский словарь переданного: `{"goal": True, "theme.type": "dark"}`.

<a id="diarysdk.models.SettingsThemeUpdate"></a>

### *модель* `diarysdk.models.SettingsThemeUpdate`

Что поменять в оформлении. Правила — как у
[`SettingsUpdate`](#diarysdk.models.SettingsUpdate).

| Поле | Тип | Что это |
| --- | --- | --- |
| `type` | `"dark"`, `"light"` | тема |
| `is_automatic` | `bool` | тема по системе |
| `color_pattern` | `"indigo"`, `"violet"`, `"pink"` | цвет |

## Карточка

Результат [`identity()`](diarysdk.md#diarysdk.Student.identity): личные данные
ученика (или родителя), документы, контакты и законные представители.

> [!CAUTION]
> Карточка содержит персональные данные: СНИЛС, документы, адреса, телефоны.
> Храните и передавайте её так же осторожно, как токен.

<a id="diarysdk.models.Identity"></a>

### *модель* `diarysdk.models.Identity`

| Поле | Тип | Что это |
| --- | --- | --- |
| `person` | [`IdentityPerson`](#diarysdk.models.IdentityPerson) | сам человек; **всегда** |
| `school` | [`SchoolBrief`](#diarysdk.models.SchoolBrief) | школа (у родителя пустая); **всегда** |
| `class_` | [`ClassUnit`](#diarysdk.models.ClassUnit) | класс (у родителя пустой); в JSON — `class`; **всегда** |
| `representatives` | `list[`[`Representative`](#diarysdk.models.Representative)`]` | законные представители |

<a id="diarysdk.models.IdentityBase"></a>

### *модель* `diarysdk.models.IdentityBase`

Общее у ученика и представителя.

| Поле | Тип | Что это |
| --- | --- | --- |
| `last_name`, `first_name`, `middle_name` | `str` | ФИО, из [`PersonName`](#diarysdk.models.PersonName) |
| `birth_date` | `date` | дата рождения |
| `sex` | `str` | пол |
| `phone` | `str` | телефон |
| `email` | `str` | почта |
| `snils` | `str` | СНИЛС |

<a id="diarysdk.models.IdentityPerson"></a>

### *модель* `diarysdk.models.IdentityPerson`

Человек в карточке. Наследует поля
[`IdentityBase`](#diarysdk.models.IdentityBase).

| Поле | Тип | Что это |
| --- | --- | --- |
| `last_name`, `first_name`, `middle_name`, `birth_date`, `sex`, `phone`, `email`, `snils` | | из [`IdentityBase`](#diarysdk.models.IdentityBase) |
| `grade_book` | [`GradeBook`](#diarysdk.models.GradeBook) | личное дело; **всегда** |
| `health` | [`Health`](#diarysdk.models.Health) | здоровье; **всегда** |
| `education_level_id` | `int` | уровень образования, код дневника |
| `service_type_id` | `int` | вид услуги, код дневника |
| `parallel_curriculum_id` | `int` | учебный план параллели |
| `specialty` | [`Specialty`](#diarysdk.models.Specialty) | специальность; **всегда** |
| `user_id` | `int` | id пользователя |
| `sudir_login` | `str` | логин СУДИР |
| `sudir_account_exists` | `bool` | учётная запись СУДИР есть |
| `is_legal_representative` | `bool` | законный представитель |
| `groups` | `list[`[`StudyGroup`](#diarysdk.models.StudyGroup)`]` | учебные группы; их id принимает [`work_program()`](diarysdk.md#diarysdk.Student.work_program) |
| `birthplace` | `str` | место рождения |
| `citizenship_id` | `int` | гражданство, код дневника |
| `documents` | `list[`[`Document`](#diarysdk.models.Document)`]` | документы |
| `addresses` | `list[`[`Address`](#diarysdk.models.Address)`]` | адреса |
| `education` | `list[`[`Education`](#diarysdk.models.Education)`]` | история обучения |
| `contacts` | `list[`[`Contact`](#diarysdk.models.Contact)`]` | контакты; их id принимает [`update_contact()`](diarysdk.md#diarysdk.Student.update_contact) |
| `categories`, `agents`, `preventions`, `citizenship`, `children` | JSON как есть | в наблюдениях всегда `None` |

Поля из карточки человека (`birthplace` и ниже), если она не далась, — `None` и
пустые списки.

<a id="diarysdk.models.Representative"></a>

### *модель* `diarysdk.models.Representative`

Законный представитель ученика.

| Поле | Тип | Что это |
| --- | --- | --- |
| `last_name`, `first_name`, `middle_name`, `birth_date`, `sex`, `phone`, `email`, `snils` | | из [`IdentityBase`](#diarysdk.models.IdentityBase) |
| `type` | `str` | кто: мать, отец, опекун — как в дневнике |
| `type_id` | `int` | код типа |
| `guid` | `str` | GUID |

<a id="diarysdk.models.GradeBook"></a>

### *модель* `diarysdk.models.GradeBook`

Личное дело.

| Поле | Тип | Что это |
| --- | --- | --- |
| `number` | `str` | номер |
| `date` | `date` | дата |

<a id="diarysdk.models.Health"></a>

### *модель* `diarysdk.models.Health`

| Поле | Тип | Что это |
| --- | --- | --- |
| `pe_group_id` | `int` | группа здоровья для физкультуры, код дневника |

<a id="diarysdk.models.Specialty"></a>

### *модель* `diarysdk.models.Specialty`

| Поле | Тип | Что это |
| --- | --- | --- |
| `code` | `str` | код |
| `name` | `str` | название |

<a id="diarysdk.models.StudyGroup"></a>

### *модель* `diarysdk.models.StudyGroup`

Учебная группа.

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id для [`work_program()`](diarysdk.md#diarysdk.Student.work_program) |
| `name` | `str` | название |
| `subject_id` | `int` | предмет |
| `is_fake` | `bool` | признак дневника `is_fake` |

<a id="diarysdk.models.Document"></a>

### *модель* `diarysdk.models.Document`

Документ.

| Поле | Тип | Что это |
| --- | --- | --- |
| `type_id` | `int` | тип, код дневника |
| `type` | `str` | название типа («Свидетельство о рождении») |
| `series` | `str` | серия |
| `number` | `str` | номер |
| `issuer` | `str` | кем выдан |
| `issued` | `date` | когда выдан |
| `expiration` | `date` | действителен до |
| `subdivision_code` | `str` | код подразделения |
| `act` | [`DocumentAct`](#diarysdk.models.DocumentAct) | актовая запись; **всегда** |
| `comment` | `str` | комментарий |
| `attachments` | `list[`[`DocumentAttachment`](#diarysdk.models.DocumentAttachment)`]` | вложения |

<a id="diarysdk.models.DocumentAct"></a>

### *модель* `diarysdk.models.DocumentAct`

Актовая запись.

| Поле | Тип | Что это |
| --- | --- | --- |
| `number` | `str` | номер |
| `date` | `date` | дата |

<a id="diarysdk.models.DocumentAttachment"></a>

### *модель* `diarysdk.models.DocumentAttachment`

Файл документа.

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `str` | id |
| `name` | `str` | имя |
| `uploaded_at` | `datetime` | когда загружен |

<a id="diarysdk.models.Address"></a>

### *модель* `diarysdk.models.Address`

| Поле | Тип | Что это |
| --- | --- | --- |
| `type_id` | `int` | тип, код дневника |
| `type` | `str` | название типа |
| `address` | `str` | адрес |
| `flat` | `str` | квартира |

<a id="diarysdk.models.Education"></a>

### *модель* `diarysdk.models.Education`

Запись истории обучения. У формы, финансирования, вида услуги и причины
выбытия — названия из ответа дневника.

| Поле | Тип | Что это |
| --- | --- | --- |
| `organization_id` | `int` | школа |
| `class_` | [`EducationClass`](#diarysdk.models.EducationClass) | класс; в JSON — `class`; **всегда** |
| `form` | `str` | форма обучения |
| `financing` | `str` | финансирование |
| `service_type` | `str` | вид услуги |
| `deduction_reason` | `str` | причина выбытия |
| `began`, `ended` | `date` | начало и конец |
| `notes` | `str` | примечания |

<a id="diarysdk.models.EducationClass"></a>

### *модель* `diarysdk.models.EducationClass`

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id |
| `uid` | `str` | UID |
| `name` | `str` | название |
| `letter` | `str` | буква |
| `parallel` | `str` | параллель («10») |
| `academic_year_id` | `int` | учебный год, код дневника |

<a id="diarysdk.models.Contact"></a>

### *модель* `diarysdk.models.Contact`

| Поле | Тип | Что это |
| --- | --- | --- |
| `id` | `int` | id для [`update_contact()`](diarysdk.md#diarysdk.Student.update_contact) |
| `type_id` | `int` | вид, код дневника |
| `type` | `str` | вид, как в дневнике |
| `value` | `str` | значение |
| `is_default` | `bool` | основной |

<a id="diarysdk.models.ContactUpdate"></a>

### *модель* `diarysdk.models.ContactUpdate`

Тело `PUT /v1/identity/contacts/{id}`: новый адрес почты. Больше ничего менять
нельзя — лишние поля (в том числе `is_default`) дают ошибку.

| Поле | Тип | Что это |
| --- | --- | --- |
| `value` | `str` | адрес: 3–255 символов, ровно одна `@` с непустыми частями, без пробелов и управляющих символов; **всегда** |
