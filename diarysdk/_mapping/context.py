"""StudentContext из family/web/v1/profile."""

from datetime import datetime

from diarysdk._port import StudentContext
from diarysdk._wire.web import Child, WebFamilyProfile
from diarysdk.errors import MultipleChildren, NotFound, UpstreamFormat


def the_child(profile: WebFamilyProfile, child_id: int | None = None) -> Child:
    """Ученик профиля: выбранный по id или единственный."""
    children = profile.children or []
    if child_id is not None:
        found = next((child for child in children if child.id == child_id), None)
        if found is None:
            raise NotFound("Такого ученика у этого токена нет")
        return found
    if len(children) > 1:
        raise MultipleChildren()
    if not children:
        raise UpstreamFormat(problems=["children: пусто — в профиле нет ученика"])
    return children[0]


def student_context(
    profile: WebFamilyProfile, expires_at: datetime, child_id: int | None = None
) -> StudentContext:
    child = the_child(profile, child_id)
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
    parent = profile.profile is not None and profile.profile.type == "parent"
    return StudentContext(
        **values,
        expires_at=expires_at,
        parallel_curriculum_id=child.parallel_curriculum_id,
        access="parent" if parent else "student",
        parent_profile_id=values["profile_id"] if parent else None,
    )
