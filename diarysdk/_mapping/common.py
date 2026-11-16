"""Разбор значений, которые дневник отдаёт как придётся: строки, даты, числа."""

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, JsonValue

from diarysdk._clock import MOSCOW
from diarysdk._wire.web import Child
from diarysdk.models.common import ClassUnit, Material, SchoolBrief


def as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def as_datetime(value: Any) -> datetime | None:
    """Время с поясом; время без пояса и голую дату дневник отдаёт по Москве."""
    if isinstance(value, str) and value:
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if isinstance(value, date) and not isinstance(value, datetime):
        # Голая дата — полночь по Москве, как и дата-строка без времени.
        value = datetime.combine(value, time.min)
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=MOSCOW)


def as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def as_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    return str(value)


def as_int(value: Any) -> int | None:
    """Целое из поля, тип которого живой ответ не подтвердил: число, целое с
    плавающей точкой или строка из цифр; иначе None, а не ошибка ответа."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        # isdigit пропускает «--5» и «²»: int() на них падает, а это не число, не ошибка.
        try:
            return int(value)
        except ValueError:
            return None
    return None


def school_brief(child: Child) -> SchoolBrief:
    school = child.school
    if school is None:
        return SchoolBrief()
    return SchoolBrief(
        id=school.id, name=school.name, short_name=school.short_name, municipality=school.county
    )


def class_unit(child: Child) -> ClassUnit:
    return ClassUnit(id=child.class_unit_id, name=child.class_name, level=child.class_level_id)


def field(source: Any, name: str) -> Any:
    """Поле модели ответа или ключ сырого словаря; нет — None."""
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def as_json(value: Any) -> JsonValue:
    """Поле «как пришло»: если он уже разобран в модель, возвращаем её JSON."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, list):
        return [as_json(item) for item in value]
    if isinstance(value, dict):
        return {key: as_json(item) for key, item in value.items()}
    return value


def average(value: Any) -> float | None:
    """Средний балл дневника. «0.00» значит «оценок нет»: настоящий средний
    по пятибалльной шкале нулём быть не может."""
    number = as_float(value)
    return None if not number else number


def materials(items: Any) -> list[Material]:
    """Вложения и материалы: в моделях ответов это нетипизированные списки,
    поэтому берём только объекты с названием или ссылкой."""
    result = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        urls = item.get("urls")
        first_url = (
            urls[0].get("url")
            if isinstance(urls, list) and urls and isinstance(urls[0], dict)
            else None
        )
        title = item.get("title") or item.get("name")
        url = item.get("url") or first_url or item.get("link")
        if title or url:
            result.append(
                Material(
                    title=title,
                    url=url,
                    description=as_text(item.get("description")),
                    content_type=as_text(item.get("content_type")),
                    type_name=as_text(item.get("type_name")),
                    action_name=as_text(item.get("action_name")),
                )
            )
    return result
