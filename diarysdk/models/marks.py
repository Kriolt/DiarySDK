import datetime as dt

from pydantic import Field, JsonValue

from diarysdk.models.common import PersonName, Schema, Subject


class Mark(Schema):
    id: int | None = None
    # dt.date, а не date: поле с именем date затенило бы тип в теле класса.
    date: dt.date | None = None
    subject: Subject | None = None
    # Оценка как в дневнике, строкой: «9», бывает «зч».
    value: str | None = None
    # Система оценивания из дневника (в гимназии десятибалльная).
    scale: str | None = None
    # Пересчёт самого дневника; своего пересчёта не делаем.
    five: float | None = None
    hundred: float | None = None
    weight: int | None = None
    control_form: str | None = None
    comment: str | None = None
    is_exam: bool | None = None
    is_point: bool | None = None
    point_date: dt.date | None = None
    created_at: dt.datetime | None = None
    # Пересчёт в десятибалльную — дневник его всё-таки отдаёт (по наблюдениям).
    ten: float | None = None
    # Наибольшая оценка шкалы.
    nmax: float | None = None
    has_files: bool | None = None
    updated_at: dt.datetime | None = None
    # Как пришло: в наблюдениях всегда пустой список, форма не подтверждена.
    criteria: JsonValue = None


class FinalMark(Schema):
    """Годовая оценка по предмету за учебный год."""

    subject: Subject | None = None
    # Как в дневнике, строкой: «7», «Зч»; null — оценки нет.
    year_mark: str | None = None
    # Промежуточная аттестация и учебные сборы: поля дневника, в наблюдении
    # пустые за все годы.
    attestation_mark: str | None = None
    training_camp_mark: str | None = None


class MarkLesson(Schema):
    topic: str | None = None
    schedule_item_id: int | None = None


class MarkDistribution(Schema):
    """Сколько учеников класса получили оценку value: число и доля, без имён и ID."""

    value: str | None = None
    students: int | None = None
    percent: int | None = None


class ClassResults(Schema):
    total_students: int | None = None
    distribution: list[MarkDistribution] = Field(default_factory=list)


class MarkDetail(Schema):
    """Одна оценка подробно: учитель, урок, итоги класса за работу.

    Источник живым ответом не подтверждён, форма — по другим клиентам; не подтверждена.
    """

    id: int | None = None
    # Оценка как в дневнике, строкой; five — пересчёт самого дневника.
    value: str | None = None
    five: float | None = None
    weight: int | None = None
    control_form: str | None = None
    comment: str | None = None
    is_exam: bool | None = None
    is_point: bool | None = None
    point_date: dt.date | None = None
    date: dt.date | None = None
    teacher: PersonName | None = None
    lesson: MarkLesson | None = None
    # Итоги класса за эту работу: только числа.
    class_results: ClassResults | None = None
    # Как пришли: формы живой ответ не подтвердил.
    criteria: JsonValue = None
    history: JsonValue = None
    result_files: JsonValue = None


class AcademicDebt(Schema):
    """Академическая задолженность ученика по предмету за учебный год.

    Форма не подтверждена: живые ответы были пустыми, поля — по тому, что
    читает сайт. Попытки пересдачи — как пришли.
    """

    subject: Subject
    # Итоговая оценка, по которой возник долг (как пришла).
    original_final_mark: JsonValue = None
    # Сайт: «аттестован» — есть итоговая или оценка хоть в одной попытке.
    attested: bool
    attempts: JsonValue = None
