"""/v1/notifications из family/mobile/v1/notifications/search.

created_at/updated_at записи — служебные, student_profile_id — свой профиль:
их не берём. Новые сверху, без даты — в конце.
"""

from diarysdk._mapping.common import as_date, as_datetime, as_text
from diarysdk._wire.mobile import Notification as WireNotification
from diarysdk.models.notifications import Notification, NotificationHomework, NotificationMark


def _notification(item: WireNotification) -> Notification:
    mark = NotificationMark(
        old=as_text(item.old_mark_value),
        new=as_text(item.new_mark_value),
        weight=item.new_mark_weight,
        is_exam=item.new_is_exam,
        control_form=item.control_form_name,
    )
    homework = NotificationHomework(
        description=item.new_hw_description,
        assigned_on=as_date(item.new_date_assigned_on),
        due=as_date(item.new_date_prepared_for),
    )
    return Notification(
        at=as_datetime(item.datetime),
        event_type=item.event_type,
        subject_name=item.subject_name,
        teacher_name=item.teacher_name,
        author_profile_id=item.author_profile_id,
        lesson_date=as_date(item.lesson_date),
        mark=mark if _has_value(mark) else None,
        homework=homework if _has_value(homework) else None,
    )


def _has_value(part: NotificationMark | NotificationHomework) -> bool:
    """Заполнено ли хоть одно поле (у модели все поля необязательные)."""
    return any(value is not None for _, value in part)


def notifications(data: list[WireNotification]) -> list[Notification]:
    result = [_notification(item) for item in data]
    # Ключ: сначала записи с датой (False < True), среди них — новые сверху.
    return sorted(
        result,
        key=lambda n: (n.at is None, -n.at.timestamp() if n.at is not None else 0.0),
    )
