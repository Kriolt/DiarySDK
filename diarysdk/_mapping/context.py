"""StudentContext из family/web/v1/profile."""

from datetime import datetime

from diarysdk._port import StudentContext
from diarysdk._wire.web import Child, WebFamilyProfile
from diarysdk.errors import MultipleChildren, UpstreamFormat


def the_child(profile: WebFamilyProfile) -> Child:
    """Единственный ученик профиля; токен родителя с несколькими детьми — не v1."""
    children = profile.children or []
    if len(children) > 1:
        raise MultipleChildren()
    if not children:
        raise UpstreamFormat(problems=["children: пусто — в профиле нет ученика"])
    return children[0]


def student_context(profile: WebFamilyProfile, expires_at: datetime) -> StudentContext:
    child = the_child(profile)
    values = {
        "student_id": child.id,
        "person_guid": child.contingent_guid,
        # Наблюдение: с profile.id работают и family/mobile, и рейтинг.
        "profile_id": profile.profile.id if profile.profile else None,
        "class_unit_id": child.class_unit_id,
        "school_id": child.school.id if child.school else None,
    }
    missing = [name for name, value in values.items() if value is None]
    if missing:
        raise UpstreamFormat(problems=[f"{name}: нет в профиле" for name in missing])
    # Учебного плана у ученика может не быть: это не ошибка профиля.
    return StudentContext(
        **values, expires_at=expires_at, parallel_curriculum_id=child.parallel_curriculum_id
    )
