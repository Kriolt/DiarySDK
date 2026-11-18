"""Заглушка типов для `sync.py`; собрана `scripts/gen_sync_stub.py`, руками не правится."""

from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Literal, Self

import httpx

from diarysdk import Avatar, Hosts
from diarysdk.models.auth import Captcha, LoginMfa
from diarysdk.models.certificates import Certificate
from diarysdk.models.curriculum import ControlWork, Curriculum, ProgramModule, SubjectTopic
from diarysdk.models.exams import Exam
from diarysdk.models.files import DiaryFile
from diarysdk.models.homework import Homework
from diarysdk.models.identity import Identity
from diarysdk.models.lessons import Lesson
from diarysdk.models.marks import AcademicDebt, FinalMark, Mark, MarkDetail
from diarysdk.models.me import Me
from diarysdk.models.notifications import Notification
from diarysdk.models.parent import Child, JournalAck, ParentMe
from diarysdk.models.periods import PeriodDay
from diarysdk.models.rating import Rating, RatingPoint, SubjectRating
from diarysdk.models.schedule import ScheduleItem
from diarysdk.models.school import School, SchoolTeacher
from diarysdk.models.settings import Settings, SettingsUpdate
from diarysdk.models.subjects import SubjectDetail, SubjectSummary
from diarysdk.token import Token

class Login:
    def esia(self, login: str, password: str) -> Token | LoginFlow:
        """Вход через Госуслуги (ЕСИА).

        Parameters
        ----------
        login, password : str
            Логин (почта, телефон или СНИЛС) и пароль Госуслуг.

        Returns
        -------
        Token или LoginFlowLike
            Токен — если вход прошёл сразу; поток — если Госуслуги просят код
            подтверждения или капчу. Поток живёт 5 минут с последнего шага.

        Raises
        ------
        BadCredentials
            Неверный логин или пароль.
        LoginBlocked
            Госуслуги заблокировали вход.
        UnsupportedStep
            Госуслуги просят шаг, которого SDK не умеет.
        """
    def password(self, login: str, password: str) -> Token:
        """Вход по логину и паролю портала «Моя школа».

        Parameters
        ----------
        login, password : str
            Учётные данные портала; никуда, кроме запроса входа, не попадают.

        Returns
        -------
        Token
            Токен со сроком из JWT.

        Raises
        ------
        BadCredentials
            Неверный логин или пароль.
        LoginBlocked
            Вход временно заблокирован.
        """

class LoginFlow:
    def answer_captcha(self, answer: str) -> Token | LoginFlow:
        """Ответить на капчу.

        Parameters
        ----------
        answer : str
            Текст с картинки или ответ на вопрос.

        Returns
        -------
        Token или LoginFlowLike
            Токен — вход завершён; поток — Госуслуги просят следующий шаг.

        Raises
        ------
        BadCaptcha
            Неверный ответ; `error.step` — свежая капча.
        FlowExpired
            Поток истёк или закрыт.
        """
    @property
    def captcha(self) -> Captcha | None:
        """Капча (картинка или вопрос); `None`, если ждём не капчу.
        """
    def close(self) -> None:
        """Закрыть вход; повторный вызов не ошибка.
        """
    @property
    def expires_at(self) -> datetime:
        """Когда поток истечёт, если не сделать следующий шаг.
        """
    @property
    def kind(self) -> Literal['mfa', 'captcha']:
        """Чего ждёт вход: `"mfa"` — кода, `"captcha"` — ответа на капчу.
        """
    @property
    def mfa(self) -> LoginMfa | None:
        """Куда отправлен код и сколько попыток осталось; `None`, если ждём не код.
        """
    def renew_captcha(self) -> LoginFlow:
        """Получить другую картинку капчи.

        Returns
        -------
        LoginFlowLike
            Тот же поток с новой капчей.

        Raises
        ------
        FlowExpired
            Поток истёк или закрыт.
        """
    def submit_code(self, code: str) -> Token | LoginFlow:
        """Отправить код подтверждения из SMS, MAX или приложения.

        Parameters
        ----------
        code : str
            Код подтверждения.

        Returns
        -------
        Token или LoginFlowLike
            Токен — вход завершён; поток — Госуслуги просят следующий шаг.

        Raises
        ------
        BadCode
            Неверный код; `error.step` — обновлённый шаг, `error.flow` — тот же поток:
            вход жив, `mfa` обновлён, код можно отправить снова.
        FlowExpired
            Поток истёк или закрыт.
        """

class Student:
    def academic_debts(self, year: int | None = None) -> list[AcademicDebt]:
        """Академические задолженности ученика за учебный год.

        Только долги этого ученика: дневник отвечает по классу, чужие строки
        отбрасываются. Форма ответа живьём не подтверждена.

        Parameters
        ----------
        year : int, optional
            Год начала учебного года; по умолчанию — текущий.

        Returns
        -------
        list[AcademicDebt]

        Raises
        ------
        BadRequest
            Учебный год ещё не начался.
        """
    def avatar(self) -> Avatar:
        """Аватарка ученика — сама картинка.

        Returns
        -------
        Avatar

        Raises
        ------
        NoAvatar
            Аватарки нет.
        NotForRole
            Через родителя: дневник отдаёт аватарку только самому ученику.
        """
    def certificates(self) -> list[Certificate]:
        """Заявки на справки об обучении за последние два года.

        Форма ответа дневника живьём не подтверждена (списки были пустыми).

        Returns
        -------
        list[Certificate]

        Raises
        ------
        NotForRole
            Токен ученика: справки дневник отдаёт только родителю.
        """
    def control_works(self, start: date | None = None, end: date | None = None) -> list[ControlWork]:
        """Контрольные работы за период.

        Форма ответа дневника живьём не подтверждена (ответы были пустыми).

        Parameters
        ----------
        start, end : datetime.date, optional
            Границы периода включительно, даты по Москве.
            По умолчанию — весь текущий учебный год; не длиннее 366 дней.

        Returns
        -------
        list[ControlWork]

        Raises
        ------
        BadRequest
            Начало позже конца или период длиннее 366 дней.
        """
    def curriculum(self) -> Curriculum:
        """Учебный план параллели: предметы и часы по неделям.

        Returns
        -------
        Curriculum

        Raises
        ------
        NotFound
            Плана у ученика нет.
        """
    def exams(self) -> list[Exam]:
        """ОГЭ и ЕГЭ ученика (в том числе пробные).

        Returns
        -------
        list[Exam]

        Raises
        ------
        NotForRole
            Через родителя: экзамены дневник отдаёт только самому ученику.
        """
    def final_marks(self, year: int | None = None) -> list[FinalMark]:
        """Годовые оценки за учебный год.

        Parameters
        ----------
        year : int, optional
            Год начала учебного года: 2025 — это 2025/26. По умолчанию — текущий.

        Returns
        -------
        list[FinalMark]

        Raises
        ------
        BadRequest
            Учебный год ещё не начался.
        """
    def final_marks_file(self, year: int | None = None, orientation: Literal['portrait', 'landscape'] = 'portrait') -> DiaryFile:
        """PDF итоговых оценок за учебный год — как кнопка «Скачать» на сайте.

        Parameters
        ----------
        year : int, optional
            Год начала учебного года; по умолчанию — текущий.
        orientation : {"portrait", "landscape"}, default "portrait"
            Ориентация страницы.

        Returns
        -------
        DiaryFile
            Байты PDF, тип `application/pdf` и имя файла.

        Raises
        ------
        BadRequest
            Неверная ориентация или учебный год ещё не начался.
        """
    def homework(self, start: date | None = None, end: date | None = None) -> list[Homework]:
        """Домашние задания за период.

        Parameters
        ----------
        start, end : datetime.date, optional
            Границы периода включительно, даты по Москве.
            По умолчанию — от сегодня на неделю вперёд; не длиннее 31 дня.

        Returns
        -------
        list[Homework]

        Raises
        ------
        BadRequest
            Начало позже конца или период длиннее 31 дня.
        """
    def homework_done(self, homework_id: int) -> None:
        """Отметить домашнее задание выполненным.

        Parameters
        ----------
        homework_id : int
            `Homework.id` из `homework()`.

        Raises
        ------
        WriteUncertain
            Сбой сети или 502/504 во время записи: прошла ли она, неизвестно —
            перечитайте `homework()`. Запись не повторяется.
        NotForRole
            Через родителя: отмечать ДЗ может только сам ученик.
        """
    def homework_undone(self, homework_id: int) -> None:
        """Снять отметку о выполнении домашнего задания.

        Parameters
        ----------
        homework_id : int
            `Homework.id` из `homework()`.

        Raises
        ------
        WriteUncertain
            Сбой сети или 502/504 во время записи; запись не повторяется.
        NotForRole
            Через родителя: отмечать ДЗ может только сам ученик.
        """
    def identity(self) -> Identity:
        """Карточка ученика: ФИО, документы, контакты, адреса, представители.

        Returns
        -------
        Identity
            Если карточка закрыта (403) или её нет (404) — поля карточки `None`.
        """
    def lesson(self, lesson_id: int) -> Lesson:
        """Урок подробно: тема, учитель, оценки, ДЗ, материалы.

        Parameters
        ----------
        lesson_id : int
            `ScheduleItem.id` из `schedule()`.

        Returns
        -------
        Lesson

        Raises
        ------
        NotFound
            Такого урока нет.
        """
    def mark(self, mark_id: int) -> MarkDetail:
        """Оценка подробно: учитель, урок, итоги класса.

        Parameters
        ----------
        mark_id : int
            `Mark.id` из `marks()`.

        Returns
        -------
        MarkDetail

        Raises
        ------
        NotFound
            Такой оценки нет.
        """
    def marks(self, start: date | None = None, end: date | None = None) -> list[Mark]:
        """Оценки за период.

        Parameters
        ----------
        start, end : datetime.date, optional
            Границы периода включительно, даты по Москве.
            По умолчанию — с 1 сентября текущего учебного года по сегодня;
            не длиннее 366 дней.

        Returns
        -------
        list[Mark]

        Raises
        ------
        BadRequest
            Начало позже конца или период длиннее 366 дней.
        """
    def me(self) -> Me:
        """Кто ученик: ФИО, GUID, школа, класс, профиль обучения, кружки, срок токена.

        Returns
        -------
        Me
        """
    def notifications(self) -> list[Notification]:
        """Уведомления: новые оценки, ДЗ и прочее.

        Returns
        -------
        list[Notification]
        """
    def periods(self, start: date | None = None, end: date | None = None) -> list[PeriodDay]:
        """Учебные дни и каникулы по дням.

        Parameters
        ----------
        start, end : datetime.date, optional
            Границы периода включительно, даты по Москве.
            По умолчанию — весь текущий учебный год; задан один край — учебный
            год этого края; не длиннее 366 дней.

        Returns
        -------
        list[PeriodDay]

        Raises
        ------
        BadRequest
            Начало позже конца или период длиннее 366 дней.
        """
    def rating(self, on: date | None = None, subject: int | None = None) -> Rating:
        """Место ученика в рейтинге класса.

        Parameters
        ----------
        on : datetime.date, optional
            На какую дату; по умолчанию — сегодня.
        subject : int, optional
            id предмета; по умолчанию — по всем предметам.

        Returns
        -------
        Rating
            Рейтинг; если в школе он выключен — `enabled=False`.
        """
    def rating_history(self, start: date | None = None, end: date | None = None) -> list[RatingPoint]:
        """Место в рейтинге класса по дням.

        Parameters
        ----------
        start, end : datetime.date, optional
            Границы периода включительно, даты по Москве.
            По умолчанию — с начала учебного года по сегодня.

        Returns
        -------
        list[RatingPoint]

        Raises
        ------
        BadRequest
            Начало позже конца.
        """
    def rating_subjects(self, on: date | None = None) -> list[SubjectRating]:
        """Место ученика в классе по каждому предмету.

        Parameters
        ----------
        on : datetime.date, optional
            На какую дату; по умолчанию — сегодня.

        Returns
        -------
        list[SubjectRating]
        """
    def schedule(self, start: date | None = None, end: date | None = None) -> list[ScheduleItem]:
        """Уроки и события календаря за период.

        Parameters
        ----------
        start, end : datetime.date, optional
            Границы периода включительно, даты по Москве.
            По умолчанию — текущая неделя; задана одна граница — вторая через
            6 дней; не длиннее 31 дня.

        Returns
        -------
        list[ScheduleItem]

        Raises
        ------
        BadRequest
            Начало позже конца или период длиннее 31 дня.
        """
    def school(self) -> School:
        """Школа: директор, адрес, классные руководители, корпуса.

        Returns
        -------
        School
        """
    def school_teachers(self, name: str | None = None) -> list[SchoolTeacher]:
        """Учителя школы ученика.

        Parameters
        ----------
        name : str, optional
            Часть имени для поиска; по умолчанию — все учителя.

        Returns
        -------
        list[SchoolTeacher]
        """
    def settings(self) -> Settings:
        """Настройки приложения владельца токена; не задавались — все поля `None`.

        Через родителя это настройки самого родителя, общие для всех детей.

        Returns
        -------
        Settings
        """
    def subject(self, subject_id: int) -> SubjectDetail:
        """Предмет подробно: оценки по периодам, итоги.

        Parameters
        ----------
        subject_id : int
            id предмета из `subjects()`.

        Returns
        -------
        SubjectDetail

        Raises
        ------
        NotFound
            Такого предмета нет.
        """
    def subject_topics(self, subject_id: int) -> list[SubjectTopic]:
        """Темы предмета и ожидаемые результаты по ним.

        Parameters
        ----------
        subject_id : int
            id предмета из `subjects()`.

        Returns
        -------
        list[SubjectTopic]
        """
    def subjects(self) -> list[SubjectSummary]:
        """Предметы со средними баллами и оценками по периодам.

        Returns
        -------
        list[SubjectSummary]
        """
    @property
    def token(self) -> Token:
        """Токен, от имени которого идут запросы.
        """
    def update_contact(self, contact_id: int, value: str) -> None:
        """Заменить адрес почты в контакте ученика.

        Parameters
        ----------
        contact_id : int
            id контакта из `identity().person.contacts`.
        value : str
            Новый адрес: 3–255 символов, одна `@`, без пробелов.

        Raises
        ------
        BadRequest
            Значение не адрес почты (до обращения к дневнику).
        UnsupportedContact
            Контакт — не почта.
        NotFound
            Такого контакта нет.
        ForbiddenScope
            Удалённый клиент: у ключа нет разрешения `write_profile`.
        WriteUncertain
            Сбой во время записи; запись не повторяется.
        """
    def update_settings(self, update: SettingsUpdate) -> None:
        """Изменить настройки приложения: только переданные поля.

        Parameters
        ----------
        update : SettingsUpdate
            Новые значения; хотя бы одно поле.

        Raises
        ------
        SettingsMissing
            Группы настроек в дневнике нет — записывать некуда.
        SettingNotSet, SettingUnrestorable
            Поле пусто или его текущее значение SDK записать не умеет.
        WriteUncertain
            Сбой во время записи; запись не повторяется.
        """
    def work_program(self, group_id: int) -> list[ProgramModule]:
        """Рабочая программа учебной группы: разделы, темы и уроки с датами.

        Parameters
        ----------
        group_id : int
            id группы из `identity().person.groups`.

        Returns
        -------
        list[ProgramModule]
        """

class Parent:
    def acknowledge_journal(self, child_id: int, week: date | None = None) -> None:
        """Отметить «ознакомлен с дневником» за неделю.

        Неделя уже отмечена — ничего не делает (и при одновременных вызовах).
        Отметку видят учителя; отменить её нельзя.

        Parameters
        ----------
        child_id : int
            `Child.id` из `children()`.
        week : datetime.date, optional
            Любой день недели; по умолчанию — текущая.

        Raises
        ------
        BadRequest
            Неделя ещё не наступила или `child_id <= 0`.
        NotFound
            Такого ученика у родителя нет.
        WriteUncertain
            Сбой во время записи; запись не повторяется.
        """
    def avatar(self) -> Avatar:
        """Аватарка родителя.

        Returns
        -------
        Avatar

        Raises
        ------
        NoAvatar
            Аватарки нет.
        """
    def children(self) -> list[Child]:
        """Ученики, к которым у родителя есть доступ.

        Returns
        -------
        list[Child]
            Пустой список, если детей в профиле нет.
        """
    def identity(self) -> Identity:
        """Карточка родителя: документы, контакты, адреса; школы и класса нет.

        Returns
        -------
        Identity
        """
    def journal_acks(self, child_id: int, start: date | None = None, end: date | None = None) -> list[JournalAck]:
        """Отметки «ознакомлен с дневником» по неделям.

        Parameters
        ----------
        child_id : int
            `Child.id` из `children()`.
        start, end : datetime.date, optional
            Границы периода включительно, даты по Москве. По умолчанию — текущая
            неделя; начало сдвигается на понедельник; не длиннее 31 дня.

        Returns
        -------
        list[JournalAck]

        Raises
        ------
        NotFound
            Такого ученика у родителя нет.
        BadRequest
            `child_id <= 0`, начало позже конца или период длиннее 31 дня.
        """
    def me(self) -> ParentMe:
        """Профиль родителя: ФИО, тип, почта, телефон, срок токена.

        Returns
        -------
        ParentMe
        """
    def settings(self) -> Settings:
        """Настройки приложения родителя, общие для всех детей.

        Returns
        -------
        Settings
        """
    def student(self, child_id: int) -> Student:
        """Ученик родителя. Запросов не делает.

        Parameters
        ----------
        child_id : int
            `Child.id` из `children()`.

        Returns
        -------
        StudentLike
            Тот же интерфейс, что у `Diary.student`; неверный id — `NotFound` при
            первом вызове, `child_id <= 0` — `BadRequest`.
        """
    @property
    def token(self) -> Token:
        """Токен родителя, от имени которого идут запросы.
        """
    def update_contact(self, contact_id: int, value: str) -> None:
        """Заменить адрес почты в контакте родителя. Живьём не проверено.

        Parameters
        ----------
        contact_id : int
            id контакта из `identity().person.contacts`.
        value : str
            Новый адрес: 3–255 символов, одна `@`, без пробелов.

        Raises
        ------
        BadRequest
            Значение не адрес почты.
        UnsupportedContact
            Контакт — не почта.
        WriteUncertain
            Сбой во время записи; запись не повторяется.
        """
    def update_settings(self, update: SettingsUpdate) -> None:
        """Изменить настройки приложения родителя. Живьём не проверено.

        Parameters
        ----------
        update : SettingsUpdate
            Новые значения; хотя бы одно поле.

        Raises
        ------
        SettingsMissing
            Группы настроек в дневнике нет.
        WriteUncertain
            Сбой во время записи; запись не повторяется.
        """

class Diary:
    def __init__(self, *, hosts: Hosts | None = None, timeout: float = 15.0, deadline: float = 20.0, http: httpx.AsyncClient | None = None) -> None: ...
    @property
    def login(self) -> Login:
        """Вход: по паролю портала (`password`) и через Госуслуги (`esia`).
        """
    def parent(self, token: str | Token) -> Parent:
        """Родитель — владелец токена. Запросов не делает.

        Токен не родителя даёт `NotForRole` при первом вызове.

        Parameters
        ----------
        token : str или Token
            JWT дневника родителя.

        Returns
        -------
        ParentLike
            Данные родителя и доступ к его ученикам.
        """
    def student(self, token: str | Token) -> Student:
        """Ученик — владелец токена или единственный ребёнок родителя. Запросов не делает.

        Токен родителя с несколькими детьми даёт `MultipleChildren` при первом вызове:
        тогда выбирайте ребёнка через `parent(token).student(child_id)`.

        Parameters
        ----------
        token : str или Token
            JWT дневника.

        Returns
        -------
        StudentLike
            Объект для чтения и записи данных ученика.
        """
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, *exc: object) -> None: ...

class RemoteDiary:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 30.0, max_rate_wait: float = 2.0, on_token_expired: Callable[[Token], Awaitable[None] | None] | None = None, http: httpx.AsyncClient | None = None) -> None: ...
    @property
    def login(self) -> Login:
        """Вход: по паролю портала (`password`) и через Госуслуги (`esia`).
        """
    def parent(self, token: str | Token) -> Parent:
        """Родитель — владелец токена. Запросов не делает.

        Токен не родителя даёт `NotForRole` при первом вызове.

        Parameters
        ----------
        token : str или Token
            JWT дневника родителя.

        Returns
        -------
        ParentLike
            Данные родителя и доступ к его ученикам.
        """
    def student(self, token: str | Token) -> Student:
        """Ученик — владелец токена или единственный ребёнок родителя. Запросов не делает.

        Токен родителя с несколькими детьми даёт `MultipleChildren` при первом вызове:
        тогда выбирайте ребёнка через `parent(token).student(child_id)`.

        Parameters
        ----------
        token : str или Token
            JWT дневника.

        Returns
        -------
        StudentLike
            Объект для чтения и записи данных ученика.
        """
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, *exc: object) -> None: ...
